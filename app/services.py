"""Ingestion, review and confirmation.

The one rule that matters: files are renamed and library.bib is written only in
``confirm``, ``undo`` and ``delete``, which run only when the owner clicks a button.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import db
from .bibtex import Entry, render, render_library
from .config import Settings
from .extract import Extraction, Venue, check_venue, extract
from .lookup import published_version
from .names import ascii_fold, build_filename, citation_key, dedupe_filename, unique_key
from .storage import Storage

log = logging.getLogger(__name__)


LOOKUP_TYPES = ("unpublished", "article", "misc")


def add_published_version(x: Extraction) -> bool:
    """Fill journal, volume, pages and DOI from arXiv/Crossref when a published version exists.

    Returns True when the journal name came back already abbreviated.
    """
    found = published_version(x.title, x.authors[0].family if x.authors else "", x.doi, x.arxiv)
    if not found:
        return False
    abbreviated = found.pop("abbreviated", False)
    for k, v in found.items():
        setattr(x, k, v)
    ref = " ".join(str(found[k]) for k in ("journal", "volume") if found.get(k))
    x.notes = (f"Published version found online: {ref} ({found.get('year', '')}). "
               "Check it. " + x.notes).strip()
    return abbreviated


class Library:
    def __init__(self, conn: sqlite3.Connection, storage: Storage, settings: Settings):
        self.conn, self.storage, self.settings = conn, storage, settings
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        # One connection is shared by page requests and the extraction threads:
        # every write (and its commit) happens under this lock.
        self.lock = threading.RLock()
        self._clean_cache()
        self._venues_path = settings.data_dir / "venues.json"
        self._venues_lock = threading.Lock()

    # ---- venues ------------------------------------------------------------
    def venue(self, name: str) -> Venue:
        """Is this a real journal, and its ISO 4 abbreviation. Asked once per name."""
        with self._venues_lock:
            cache = (json.loads(self._venues_path.read_text(encoding="utf-8"))
                     if self._venues_path.exists() else {})
        if name in cache:
            return Venue(**cache[name])
        v = check_venue(name, self.settings.gemini_api_key, self.settings.gemini_model)
        with self._venues_lock:
            cache = (json.loads(self._venues_path.read_text(encoding="utf-8"))
                     if self._venues_path.exists() else {})
            cache[name] = v.model_dump()
            self._venues_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False),
                                         encoding="utf-8")
        return v

    def fix_venue(self, x: Extraction) -> None:
        """Abbreviate real journals; move books and proceedings out of ``journal``."""
        try:
            v = self.venue(x.journal)
        except Exception as exc:  # noqa: BLE001 - keep the proposal as is
            log.warning("venue check failed for %r: %s", x.journal, exc)
            return
        if v.kind == "journal":
            if v.abbreviation:
                x.journal = v.abbreviation
        elif v.kind in ("book", "proceedings"):
            x.notes = (f"'{x.journal}' is a {v.kind}, not a journal: saved as "
                       f"{'a chapter' if v.kind == 'book' else 'a conference paper'}. "
                       + x.notes).strip()
            x.booktitle = x.booktitle or x.journal
            x.journal = ""
            x.entry_type = "incollection" if v.kind == "book" else "inproceedings"
        else:
            x.notes = (f"Could not confirm that '{x.journal}' is a journal. "
                       + x.notes).strip()

    # ---- files -------------------------------------------------------------
    def pdf_path(self, file_id: str) -> Path:
        """The PDF on disk: the file itself locally, a cached download for Drive."""
        if (local := self.storage.local_path(file_id)) is not None:
            return local
        path: Path = self.settings.cache_dir / f"{file_id}.pdf"
        if not path.exists():
            path.write_bytes(self.storage.download(file_id))
        return path

    def pdf_bytes(self, file_id: str) -> bytes:
        return self.pdf_path(file_id).read_bytes()

    def _clean_cache(self) -> None:
        """Drop cached previews and downloads of papers that no longer exist."""
        known = {r[0] for r in self.conn.execute("SELECT file_id FROM papers")}
        local = self.settings.storage == "local"
        for f in self.settings.cache_dir.iterdir():
            if f.is_file() and f.stem not in known or (local and f.suffix == ".pdf"):
                f.unlink(missing_ok=True)

    def _forget_cache(self, file_id: str) -> None:
        for ext in (".pdf", ".png"):
            (self.settings.cache_dir / f"{file_id}{ext}").unlink(missing_ok=True)

    def get(self, paper_id: int) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if row is None:
            raise KeyError(paper_id)
        return row

    def taken_keys(self, exclude: int | None = None) -> set[str]:
        rows = self.conn.execute(
            "SELECT id, entry_json FROM papers WHERE status IN ('staged', 'confirmed') "
            "AND entry_json IS NOT NULL"
        ).fetchall()
        return {json.loads(r["entry_json"])["key"] for r in rows if r["id"] != exclude}

    # ---- ingestion (read-only on storage) ---------------------------------
    def register(self, file_id: str, name: str) -> bool:
        with self.lock:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO papers (file_id, original_filename, filename) "
                "VALUES (?, ?, ?)", (file_id, name, name),
            )
            self.conn.commit()
        return cur.rowcount == 1

    def scan(self) -> int:
        return sum(self.register(f.id, f.name) for f in self.storage.list_new_pdfs())

    def upload(self, name: str, data: bytes) -> None:
        f = self.storage.save_upload(name, data)
        self.register(f.id, f.name)

    def process_pending(self, workers: int = 4) -> int:
        """Extract several papers at once; results are stored one by one as they land."""
        rows = self.conn.execute("SELECT id FROM papers WHERE status = 'pending'").fetchall()
        tags = [t["name"] for t in db.all_tags(self.conn)]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._extract, self.get(r["id"]), tags): r["id"]
                       for r in rows}
            for fut in as_completed(futures):
                self._store(futures[fut], fut.result())
        return len(rows)

    def propose(self, paper_id: int) -> None:
        """Run extraction and stage the proposal. Never touches the file."""
        tags = [t["name"] for t in db.all_tags(self.conn)]
        self._store(paper_id, self._extract(self.get(paper_id), tags))

    def _extract(self, row: sqlite3.Row, tags: list[str]) -> Extraction | Exception:
        start = time.monotonic()
        log.info("reading %s", row["original_filename"])
        try:
            x = extract(self.pdf_bytes(row["file_id"]), tags,
                        self.settings.gemini_api_key, self.settings.gemini_model)
            abbreviated = False
            if (self.settings.online_lookup and x.entry_type in LOOKUP_TYPES
                    and (not x.journal or x.entry_type == "unpublished")):
                abbreviated = add_published_version(x)
            if x.journal and self.settings.gemini_api_key and not abbreviated:
                self.fix_venue(x)
            log.info("done %s in %.1fs", row["original_filename"], time.monotonic() - start)
            return x
        except Exception as exc:  # noqa: BLE001 - shown to the user on the staging page
            log.exception("extraction failed for %s", row["original_filename"])
            return exc

    def _store(self, paper_id: int, x: Extraction | Exception) -> None:
        with self.lock:
            self._store_locked(paper_id, x)

    def _store_locked(self, paper_id: int, x: Extraction | Exception) -> None:
        if not self.conn.execute("SELECT 1 FROM papers WHERE id = ?", (paper_id,)).fetchone():
            return  # deleted while it was being read
        if isinstance(x, Exception):
            self.conn.execute("UPDATE papers SET status = 'error', error = ? WHERE id = ?",
                              (str(x)[:500], paper_id))
            self.conn.commit()
            return
        if dup := self.find_duplicate(paper_id, x.title, x.doi):
            x.notes = (f"Possible duplicate of {dup}. " + x.notes).strip()
        fields = x.model_dump(exclude={"tags", "new_tags", "notes", "needs_more_pages"})
        entry = Entry(key=unique_key(citation_key(x.authors, x.year),
                                     self.taken_keys(exclude=paper_id)), **fields)
        self.conn.execute(
            "UPDATE papers SET status = 'staged', entry_json = ?, proposal_json = ?, "
            "proposed_filename = ?, notes = ?, error = NULL, bibtex = ?, bibtex_override = 0 "
            "WHERE id = ?",
            (entry.model_dump_json(), x.model_dump_json(),
             build_filename(entry.year, entry.authors, entry.title), x.notes,
             render(entry), paper_id),
        )
        existing = [t["name"] for t in db.all_tags(self.conn)]
        db.set_paper_tags(self.conn, paper_id,
                          [db.match_tag(t, existing) for t in x.tags + x.new_tags[:2]])
        self.conn.commit()

    def find_duplicate(self, paper_id: int, title: str, doi: str) -> str | None:
        def norm(t: str) -> str:
            return re.sub(r"[^a-z0-9]", "", ascii_fold(t).lower())

        rows = self.conn.execute(
            "SELECT id, filename, entry_json FROM papers WHERE id != ? AND entry_json IS NOT NULL "
            "AND status IN ('staged', 'confirmed')", (paper_id,)).fetchall()
        for r in rows:
            e = json.loads(r["entry_json"])
            if (doi and e.get("doi") == doi) or (title and norm(e["title"]) == norm(title)):
                return r["filename"]
        return None

    def save_draft(self, paper_id: int, entry: Entry, filename: str, bibtex: str,
                   tags: list[str]) -> None:
        override = bibtex.strip() != render(entry).strip()
        with self.lock:
            self.conn.execute(
                "UPDATE papers SET entry_json = ?, proposed_filename = ?, bibtex = ?, "
                "bibtex_override = ? WHERE id = ?",
                (entry.model_dump_json(), filename, bibtex.strip(), int(override), paper_id),
            )
            db.set_paper_tags(self.conn, paper_id, tags)
            self.conn.commit()

    def delete(self, paper_id: int) -> None:
        """Move the PDF to the trash and forget the paper; drop it from library.bib."""
        with self.lock:
            row = self.get(paper_id)
            self.storage.trash(row["file_id"])
            self._forget_cache(row["file_id"])
            self.conn.execute("DELETE FROM paper_tags WHERE paper_id = ?", (paper_id,))
            self.conn.execute("DELETE FROM papers_fts WHERE rowid = ?", (paper_id,))
            self.conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
            self.conn.commit()
            if row["status"] == "confirmed":
                self.write_bib()

    def delete_all_in_review(self) -> int:
        """Delete every paper waiting in Review (the Delete all button)."""
        with self.lock:
            ids = [r[0] for r in self.conn.execute(
                "SELECT id FROM papers WHERE status IN ('pending', 'staged', 'error')")]
            for paper_id in ids:
                self.delete(paper_id)
        return len(ids)

    # ---- the only writes to storage ---------------------------------------
    def confirm(self, paper_id: int, entry: Entry, filename: str, bibtex: str,
                tags: list[str]) -> str:
        """Rename the file, then record it and rewrite library.bib."""
        with self.lock:
            row = self.get(paper_id)
            if entry.key in self.taken_keys(exclude=paper_id):
                raise ValueError(f"Citation key {entry.key} is already used.")
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"
            names = self.storage.list_library_names()
            if row["status"] == "confirmed":
                names.discard(row["filename"])
            filename = dedupe_filename(filename, names)
            self.storage.rename(row["file_id"], filename, to_library=True)
            self.save_draft(paper_id, entry, filename, bibtex, tags)
            self.conn.execute(
                "UPDATE papers SET status = 'confirmed', filename = ?, "
                "confirmed_at = CURRENT_TIMESTAMP WHERE id = ?", (filename, paper_id),
            )
            db.reindex(self.conn, paper_id)
            self.conn.commit()
            self.write_bib()
        return filename

    def undo(self, paper_id: int) -> None:
        with self.lock:
            row = self.get(paper_id)
            self.storage.rename(row["file_id"], row["original_filename"], to_library=False)
            self.conn.execute(
                "UPDATE papers SET status = 'staged', filename = original_filename, "
                "confirmed_at = NULL WHERE id = ?", (paper_id,),
            )
            db.reindex(self.conn, paper_id)
            self.conn.commit()
            self.write_bib()

    def write_bib(self) -> None:
        self.storage.write_bib(self.bib_text())

    def bib_text(self, paper_ids: list[int] | None = None) -> str:
        rows = self.conn.execute(
            "SELECT id, bibtex, entry_json FROM papers WHERE status = 'confirmed'"
        ).fetchall()
        if paper_ids is not None:
            wanted = set(paper_ids)
            rows = [r for r in rows if r["id"] in wanted]
        rows.sort(key=lambda r: json.loads(r["entry_json"])["key"].lower())
        return render_library([r["bibtex"] for r in rows]) if rows else ""

    # ---- search -------------------------------------------------------------
    def _search_sql(self, q: str, tags: list[str]) -> tuple[str, list, str]:
        sql = " FROM papers p"
        args: list = []
        where = ["p.status = 'confirmed'"]
        if q.strip():
            sql += " JOIN papers_fts f ON f.rowid = p.id"
            where.append("papers_fts MATCH ?")
            args.append(db.fts_query(q))
        for t in tags:
            where.append("EXISTS (SELECT 1 FROM paper_tags pt JOIN tags t ON t.id = pt.tag_id "
                         "WHERE pt.paper_id = p.id AND t.name = ?)")
            args.append(t)
        sql += " WHERE " + " AND ".join(where)
        order = " ORDER BY f.rank" if q.strip() else " ORDER BY p.confirmed_at DESC, p.id DESC"
        return sql, args, order

    def search(self, q: str = "", tags: list[str] | None = None,
               limit: int = -1, offset: int = 0) -> list[sqlite3.Row]:
        sql, args, order = self._search_sql(q, tags or [])
        return self.conn.execute("SELECT p.*" + sql + order + " LIMIT ? OFFSET ?",
                                 [*args, limit, offset]).fetchall()

    def count(self, q: str = "", tags: list[str] | None = None) -> int:
        sql, args, _ = self._search_sql(q, tags or [])
        return self.conn.execute("SELECT COUNT(*)" + sql, args).fetchone()[0]
