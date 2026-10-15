---
name: research-library-builder
description: Use when building, extending, debugging or deploying the Research Library app (FastAPI + Tailwind paper classifier with Google Drive, Gemini and BibTeX).
---

# Research Library builder

Private web app: PDFs land in a Drive `Inbox/`, Gemini proposes metadata, the owner reviews it on the Staging screen, and only **Confirm & Rename** renames the file, moves it to the library folder and rewrites `library.bib`.

## Before you start
1. Read `PLAN.md` (objectives, decisions, checklist) and `docs/bibtex-style.md` (Billy's house style). They override anything here.
2. Take the next unchecked checklist item unless the user named one; tick it when done.

## Hard rules
- **Never rename, move or finalize automatically.** Storage writes (`rename`, `write_bib`) are called only from `Library.confirm` / `Library.undo` in `app/services.py`. `tests/test_flow.py::test_scan_never_renames` guards this; keep it passing.
- Address files by ID, never by name.
- Confirm order: rename in storage first, then DB, then `library.bib`.
- Secrets only via env vars (`.env.example` documents them).
- Every route except `/login`, `/auth/callback` and `/static` requires the owner (`get_library` depends on `require_owner`).

## Map
| File | What |
|---|---|
| `app/names.py` | author parsing, particles, citation keys, Windows-safe filenames |
| `app/bibtex.py` | `Entry` model and house-style rendering, field order per type |
| `app/extract.py` | Gemini extraction (JSON schema), no-AI fallback, page-1 preview |
| `app/storage.py` | `DriveStorage` (Drive API v3) and `LocalStorage` (folder on disk) |
| `app/services.py` | scan / propose / confirm / undo / search |
| `app/db.py` | SQLite + FTS5 (accent-insensitive), tags and colors |
| `app/main.py` | routes; `app/templates/` Jinja + Tailwind + htmx |

## Workflow
1. Tests first for pure logic; Billy's four examples in `tests/test_names_bibtex.py` must render exactly.
2. `pip install -r requirements-dev.txt`, then `pytest -q` and `ruff check .`.
   Keep it minimal and fast (Billy's priority): no new dependency for the local version without a strong reason.
3. Try it: `AUTH_DISABLED=1 STORAGE=local uvicorn app.main:app --reload`, drop PDFs into `data/library/Inbox`, click Scan inbox.
4. After changing classes in templates rebuild CSS: `npx tailwindcss@3.4.16 -c frontend/tailwind.config.js -i frontend/input.css -o app/static/app.css --minify`.
5. Update `PLAN.md`.
