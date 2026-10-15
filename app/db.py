"""SQLite metadata store with FTS5 search.

The database is a cache: Drive holds the PDFs and library.bib, and every
confirmed paper can be rebuilt from them.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY,
    file_id TEXT UNIQUE NOT NULL,
    original_filename TEXT NOT NULL,
    filename TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending|staged|confirmed|skipped|error
    entry_json TEXT,       -- current (possibly edited) bibtex.Entry
    proposal_json TEXT,    -- untouched AI proposal
    bibtex TEXT,           -- final text written to library.bib
    bibtex_override INTEGER NOT NULL DEFAULT 0,
    proposed_filename TEXT,
    notes TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TEXT
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    color TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_tags (
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, tag_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    title, authors, year, citation_key, tags, filename,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

PALETTE = ["blue", "emerald", "amber", "rose", "violet", "cyan", "lime", "orange",
           "fuchsia", "teal", "sky", "pink"]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def color_for(name: str) -> str:
    return PALETTE[sum(map(ord, name)) % len(PALETTE)]


def tag_name(text: str) -> str:
    """Lowercase-kebab, ASCII: ``Lie Algebroids`` -> ``lie-algebroids``."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower().strip()
    text = re.sub(r"[^a-z0-9-]", "", re.sub(r"[\s_]+", "-", text))
    return re.sub(r"-+", "-", text).strip("-")


def ensure_tag(conn: sqlite3.Connection, name: str) -> int:
    name = tag_name(name)
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    return conn.execute(
        "INSERT INTO tags (name, color) VALUES (?, ?)", (name, color_for(name))
    ).lastrowid


def set_paper_tags(conn: sqlite3.Connection, paper_id: int, names: list[str]) -> None:
    conn.execute("DELETE FROM paper_tags WHERE paper_id = ?", (paper_id,))
    for name in {tag_name(n) for n in names} - {""}:
        conn.execute(
            "INSERT OR IGNORE INTO paper_tags VALUES (?, ?)", (paper_id, ensure_tag(conn, name))
        )


def paper_tags(conn: sqlite3.Connection, paper_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT t.* FROM tags t JOIN paper_tags pt ON pt.tag_id = t.id "
        "WHERE pt.paper_id = ? ORDER BY t.name",
        (paper_id,),
    ).fetchall()


def all_tags(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT t.*, COUNT(p.id) AS n FROM tags t "
        "LEFT JOIN paper_tags pt ON pt.tag_id = t.id "
        "LEFT JOIN papers p ON p.id = pt.paper_id AND p.status = 'confirmed' "
        "GROUP BY t.id ORDER BY t.name"
    ).fetchall()


def reindex(conn: sqlite3.Connection, paper_id: int) -> None:
    conn.execute("DELETE FROM papers_fts WHERE rowid = ?", (paper_id,))
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not row or row["status"] != "confirmed" or not row["entry_json"]:
        return
    e = json.loads(row["entry_json"])
    authors = " ".join(
        " ".join(filter(None, (a.get("given"), a.get("particle"), a.get("family"))))
        for a in e.get("authors", [])
    )
    tags = " ".join(t["name"].replace("-", " ") for t in paper_tags(conn, paper_id))
    conn.execute(
        "INSERT INTO papers_fts (rowid, title, authors, year, citation_key, tags, filename) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (paper_id, e.get("title", ""), authors, str(e.get("year") or ""), e.get("key", ""),
         tags, row["filename"]),
    )


def fts_query(text: str) -> str:
    """Turn user input into a prefix-matching FTS5 query."""
    words = [w.replace('"', "") for w in text.split() if w.replace('"', "")]
    return " ".join(f'"{w}"*' for w in words)
