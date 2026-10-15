from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from urllib.parse import urlencode

from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .auth import LoginRequired, require_owner, setup_oauth
from .auth import router as auth_router
from .bibtex import ENTRY_TYPES, Entry, render
from .config import get_settings
from .extract import render_preview
from .latex import to_unicode
from .names import Author, build_filename, citation_key, parse_author, unique_key
from .services import Library
from .storage import make_storage

settings = get_settings()
app = FastAPI(title="Research Library", docs_url=None, redoc_url=None)
if not settings.auth_disabled:
    from starlette.middleware.sessions import SessionMiddleware

    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret,
                       https_only=True, same_site="lax", max_age=60 * 60 * 24 * 30)
    app.include_router(auth_router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
setup_oauth()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["auth_on"] = not settings.auth_disabled
templates.env.globals["local"] = settings.storage == "local"
templates.env.filters["qs"] = lambda d: urlencode(d, doseq=True)
templates.env.filters["tex"] = to_unicode
templates.env.filters["names"] = lambda authors: ", ".join(
    Author(**a).display for a in authors or [])

_conn = db.connect(settings.db_path)
_library: Library | None = None
_process_lock = threading.Lock()


@app.exception_handler(LoginRequired)
async def _login_redirect(request: Request, exc: LoginRequired):
    return RedirectResponse("/login")


def get_library(_: str = Depends(require_owner)) -> Library:
    global _library
    if _library is None:
        _library = Library(_conn, make_storage(settings), settings)
    return _library


def process_in_background(lib: Library) -> None:
    if _process_lock.acquire(blocking=False):
        try:
            # Keep going while new PDFs arrive during a run.
            while lib.process_pending():
                pass
        finally:
            _process_lock.release()


def waiting() -> int:
    return _conn.execute("SELECT COUNT(*) FROM papers WHERE status IN "
                         "('pending','staged','error')").fetchone()[0]


def tag_index() -> list[dict]:
    return [{"name": t["name"], "color": t["color"], "n": t["n"]} for t in db.all_tags(_conn)]


def page(request: Request, name: str, **ctx) -> HTMLResponse:
    ctx.setdefault("tag_index", tag_index())
    ctx.setdefault("staged", waiting())
    return templates.TemplateResponse(request, name, ctx)


def entry_dict(row) -> dict:
    return json.loads(row["entry_json"]) if row["entry_json"] else {}


def authors_text(entry: dict) -> str:
    """One author per line, ``particle Family, Given``: unambiguous to parse."""
    return "\n".join(
        f"{(a.get('particle', '') + ' ' + a['family']).strip()}, {a.get('given', '')}".rstrip(", ")
        for a in entry.get("authors", [])
    )


async def entry_from_form(request: Request) -> tuple[Entry, dict]:
    form = await request.form()
    data = {k: str(v).strip() for k, v in form.items()}
    authors = [parse_author(line) for line in data.get("authors", "").splitlines() if line.strip()]
    year = int(data["year"]) if data.get("year", "").isdigit() else None
    fields = {k: data.get(k, "") for k in Entry.model_fields
              if k not in ("authors", "year", "key")}
    entry = Entry(key=data.get("key") or citation_key(authors, year), authors=authors,
                  year=year, **fields)
    return entry, data


def tag_list(data: dict) -> list[str]:
    return [t for t in data.get("tags", "").replace(",", " ").split() if t]


# ---- library ---------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def library_page(request: Request, q: str = "", tag: list[str] = Query(default=[]),
                 lib: Library = Depends(get_library)):
    tags = tag or []
    rows = lib.search(q, tags)
    ctx = dict(q=q, active=tags, papers=[(r, entry_dict(r), db.paper_tags(_conn, r["id"]))
                                         for r in rows],
               tags=db.all_tags(_conn), export_qs=urlencode({"q": q, "tag": tags}, doseq=True))
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "results":
        return page(request, "partials/results.html", **ctx)
    return page(request, "library.html", **ctx)


@app.get("/export.bib")
def export_bib(q: str = "", tag: list[str] = Query(default=[]),
               lib: Library = Depends(get_library)):
    ids = [r["id"] for r in lib.search(q, tag or [])]
    name = "export.bib" if q or tag else "library.bib"
    return PlainTextResponse(lib.bib_text(ids), headers={
        "Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/library.bib")
def master_bib(lib: Library = Depends(get_library)):
    return PlainTextResponse(lib.bib_text(), headers={
        "Content-Disposition": 'attachment; filename="library.bib"'})


@app.post("/papers/{paper_id}/tags")
async def edit_tags(request: Request, paper_id: int, lib: Library = Depends(get_library)):
    """Replace a paper's tags with the space-separated list sent by the tag editor."""
    form = await request.form()
    lib.get(paper_id)
    db.set_paper_tags(_conn, paper_id, tag_list(dict(form)))
    db.reindex(_conn, paper_id)
    _conn.commit()
    return {"tags": [t["name"] for t in db.paper_tags(_conn, paper_id)], "index": tag_index()}


@app.post("/papers/{paper_id}/undo")
def undo(paper_id: int, lib: Library = Depends(get_library)):
    lib.undo(paper_id)
    return RedirectResponse(f"/staging/{paper_id}", status_code=303)


@app.post("/quit", response_class=HTMLResponse)
def quit_app(_: Library = Depends(get_library)):
    """Stop the background server started by start.bat."""
    threading.Timer(0.5, os._exit, args=(0,)).start()
    return HTMLResponse('<body style="font:14px system-ui;color:#64748b;padding:3rem">'
                        "Research Library stopped. Open start.bat to run it again.</body>")


# ---- tags ------------------------------------------------------------------
@app.get("/tags", response_class=HTMLResponse)
def tags_page(request: Request, _: Library = Depends(get_library)):
    return page(request, "tags.html", tags=db.all_tags(_conn), palette=db.PALETTE)


@app.post("/tags/{tag_id}")
async def update_tag(request: Request, tag_id: int, _: Library = Depends(get_library)):
    form = await request.form()
    if form.get("delete"):
        affected = [r[0] for r in _conn.execute(
            "SELECT paper_id FROM paper_tags WHERE tag_id = ?", (tag_id,))]
        _conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        for pid in affected:
            db.reindex(_conn, pid)
    elif form.get("color") in db.PALETTE:
        _conn.execute("UPDATE tags SET color = ? WHERE id = ?", (form["color"], tag_id))
    _conn.commit()
    return RedirectResponse("/tags", status_code=303)


# ---- staging ---------------------------------------------------------------
@app.get("/staging", response_class=HTMLResponse)
def staging_page(request: Request, bg: BackgroundTasks, msg: str = "",
                 lib: Library = Depends(get_library)):
    if not request.headers.get("HX-Request"):
        lib.scan()
        bg.add_task(process_in_background, lib)  # also picks up anything left pending
    rows = _conn.execute(
        "SELECT * FROM papers WHERE status IN ('pending','staged','error') ORDER BY id"
    ).fetchall()
    ctx = dict(papers=[(r, entry_dict(r)) for r in rows], msg=msg,
               busy=any(r["status"] == "pending" for r in rows))
    if request.headers.get("HX-Request"):
        return page(request, "partials/staging_rows.html", **ctx)
    return page(request, "staging.html", **ctx)


@app.post("/scan")
def scan(bg: BackgroundTasks, lib: Library = Depends(get_library)):
    n = lib.scan()
    bg.add_task(process_in_background, lib)
    return RedirectResponse(f"/staging?msg=Found+{n}+new+PDF(s)", status_code=303)


@app.post("/upload")
async def upload(request: Request, files: list[UploadFile], bg: BackgroundTasks,
                 lib: Library = Depends(get_library)):
    n = 0
    for f in files:
        if f.filename and f.filename.lower().endswith(".pdf"):
            lib.upload(f.filename, await f.read())
            n += 1
    bg.add_task(process_in_background, lib)
    if "application/json" in request.headers.get("accept", ""):
        return {"added": n, "waiting": waiting()}
    return RedirectResponse(f"/staging?msg=Added+{n}+PDF(s)", status_code=303)


@app.get("/papers/{paper_id}/preview.png")
def preview(paper_id: int, lib: Library = Depends(get_library)):
    row = lib.get(paper_id)
    png = settings.cache_dir / f"{row['file_id']}.png"
    if not png.exists():
        png.write_bytes(render_preview(lib.pdf_bytes(row["file_id"])))
    return Response(png.read_bytes(), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=86400"})


@app.get("/papers/{paper_id}/file.pdf")
def pdf(paper_id: int, lib: Library = Depends(get_library)):
    row = lib.get(paper_id)
    return Response(lib.pdf_bytes(row["file_id"]), media_type="application/pdf",
                    headers={"Content-Disposition": "inline"})


def review_ctx(lib: Library, paper_id: int, error: str = "") -> dict:
    row = lib.get(paper_id)
    e = entry_dict(row)
    nxt = _conn.execute("SELECT id FROM papers WHERE status = 'staged' AND id != ? "
                        "ORDER BY id LIMIT 1", (paper_id,)).fetchone()
    return dict(paper=row, e=e, authors=authors_text(e), entry_types=ENTRY_TYPES,
                ptags=" ".join(t["name"] for t in db.paper_tags(_conn, paper_id)),
                all_tags=db.all_tags(_conn), error=error,
                proposal=json.loads(row["proposal_json"]) if row["proposal_json"] else {},
                next_id=nxt["id"] if nxt else None, view_url=lib.storage.view_url(row["file_id"]))


@app.get("/staging/{paper_id}", response_class=HTMLResponse)
def review(request: Request, paper_id: int, msg: str = "",
           lib: Library = Depends(get_library)):
    return page(request, "review.html", msg=msg, **review_ctx(lib, paper_id))


@app.post("/staging/{paper_id}/derive", response_class=HTMLResponse)
async def derive(request: Request, paper_id: int, lib: Library = Depends(get_library)):
    """Recompute key, filename and BibTeX from the edited fields (no saving)."""
    entry, _ = await entry_from_form(request)
    entry.key = unique_key(citation_key(entry.authors, entry.year), lib.taken_keys(paper_id))
    return page(request, "partials/derived.html", key=entry.key,
                filename=build_filename(entry.year, entry.authors, entry.title),
                bibtex=render(entry))


@app.post("/staging/{paper_id}/confirm", response_class=HTMLResponse)
async def confirm(request: Request, paper_id: int, lib: Library = Depends(get_library)):
    entry, data = await entry_from_form(request)
    try:
        name = lib.confirm(paper_id, entry, data.get("filename", ""),
                           data.get("bibtex") or render(entry), tag_list(data))
    except (ValueError, FileExistsError, OSError) as exc:
        lib.save_draft(paper_id, entry, data.get("filename", ""),
                       data.get("bibtex") or render(entry), tag_list(data))
        return page(request, "review.html", **review_ctx(lib, paper_id, str(exc)))
    nxt = data.get("next_id")
    target = f"/staging/{nxt}" if nxt else "/staging"
    return RedirectResponse(f"{target}?{urlencode({'msg': 'Renamed to ' + name})}",
                            status_code=303)


@app.post("/staging/{paper_id}/save")
async def save(request: Request, paper_id: int, lib: Library = Depends(get_library)):
    entry, data = await entry_from_form(request)
    lib.save_draft(paper_id, entry, data.get("filename", ""),
                   data.get("bibtex") or render(entry), tag_list(data))
    return RedirectResponse(f"/staging/{paper_id}", status_code=303)


@app.post("/staging/{paper_id}/rerun")
def rerun(paper_id: int, lib: Library = Depends(get_library)):
    lib.propose(paper_id)
    return RedirectResponse(f"/staging/{paper_id}", status_code=303)


@app.post("/staging/{paper_id}/delete")
def delete(paper_id: int, lib: Library = Depends(get_library)):
    lib.delete(paper_id)
    return RedirectResponse("/staging", status_code=303)
