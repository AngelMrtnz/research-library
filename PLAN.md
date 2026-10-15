# Research Library — Academic Paper Classifier & BibTeX Manager

_Status: MVP built and tested locally (Oct 15). Not yet deployed or run against real Drive/Gemini. Decisions marked **(default)** are placeholders until Billy confirms them (see [Open decisions](#open-decisions))._

## 1. Objectives

A private web app that turns a messy folder of PDFs in Google Drive into a clean, searchable, citable library.

1. **Storage** — Google Drive is the source of truth. The library folder is synced to Windows via Google Drive for Desktop, so a rename in Drive shows up in File Explorer.
2. **Private** — only the owner can sign in.
3. **AI extraction** — Gemini reads each new PDF and proposes title, authors, year, tags, a BibTeX entry and a standardized filename.
4. **Human in the loop** — nothing is renamed or written to the master `.bib` until the owner reviews it on a Staging screen and clicks **Confirm & Rename**.
5. **Explorer-friendly names** — e.g. `2021 - de León - Deep Learning for Soil Moisture.pdf`, safe on Windows.
6. **Master BibTeX** — one `library.bib` kept in sync with every confirmed paper, plus export of any filtered subset.
7. **Instant search** — full-text across title, authors, year, citation key (and optionally abstract / first-page text); tag filtering with colored badges.

### Non-goals (v1)
- Multi-user / sharing, citation-graph features, reading/annotation inside the app, mobile app.

## 2. Architecture

```
Browser (Tailwind + HTMX/Alpine, pdf.js preview)
        │  HTTPS, session cookie
        ▼
FastAPI app ───────────────┬──────────────► Gemini API (extraction)
  ├─ auth (Google OAuth, email allowlist)
  ├─ ingest  (scan Drive / upload)        ┌─► Google Drive API v3
  ├─ staging (review queue)  ─────────────┤     (list, download, rename, upload library.bib)
  ├─ library (search, tags, export)       │
  └─ bibtex  (key gen, formatting rules)  │
        │                                 │
        ▼                                 │
SQLite (+ FTS5) ◄─────────────────────────┘
  papers, tags, paper_tags, staging, settings, fts_papers
```

### Components
| Module | Responsibility |
|---|---|
| `app/auth.py` | Google OAuth login (Authlib), single-email allowlist, signed session cookie. |
| `app/drive.py` | Drive client: list PDFs in the library folder (+ `inbox/` subfolder), download bytes, rename by file ID, upload/overwrite `library.bib`. Uses file IDs, never paths, so renames are safe. |
| `app/extract.py` | Pull first 1–2 pages of text (pypdf/PyMuPDF) + optional DOI lookup; send to Gemini with a JSON schema; validate with Pydantic. Pass existing tag list so Gemini reuses tags. |
| `app/names.py` | Author parsing (initials + full surname, particles: de, de la, van, von, van der, del, da, di, le, bin…), filename builder, Windows sanitizer (strip `<>:"/\|?*`, trailing dots/spaces, reserved names like `CON`, max length ~150). |
| `app/bibtex.py` | Citation-key generator and BibTeX formatter driven by user rules in `settings`; writes `library.bib` deterministically (sorted by key). |
| `app/db.py` | SQLite schema + FTS5 virtual table; triggers keep FTS in sync. |
| `app/routes/` | `/staging`, `/staging/{id}` (review form), `/library` (search/filter), `/tags`, `/export.bib`, `/settings`. |
| `templates/` | Jinja2 + Tailwind; pdf.js renders page 1 thumbnail in Staging. |

### Data model (SQLite)
- `papers(id, drive_file_id UNIQUE, filename, title, authors_json, year, citation_key UNIQUE, bibtex, doi, abstract, status ['staged','confirmed'], created_at, confirmed_at)`
- `tags(id, name UNIQUE, color)` · `paper_tags(paper_id, tag_id)`
- `staging(paper_id, proposed_json, original_filename, error)` — Gemini output kept untouched next to edits
- `settings(key, value)` — filename template, BibTeX rules, citation-key pattern, Drive folder ID
- `fts_papers` — FTS5 over title, authors, year, citation_key, tags (+ abstract)

### Ingestion flow
1. **Scan**: list PDFs in the Drive library folder whose `drive_file_id` is not yet in `papers` (or a dedicated `Inbox/` folder **(default)**). **Upload**: browser upload → saved to Drive `Inbox/`.
2. Extract text → Gemini → validated proposal → row with `status='staged'`.
3. **Staging screen**: page-1 preview left, editable form right (title, authors list, year, tags chips, citation key, BibTeX textarea, filename preview with live sanitizing). Buttons: *Re-run AI*, *Skip*, **Confirm & Rename**.
4. On confirm: check filename collision → Drive `files.update(name=…)` (optionally move from `Inbox/` to library root) → set `status='confirmed'` → regenerate and upload `library.bib`. All in one step; if Drive fails, DB is not changed.
5. Undo: keep `original_filename` so a confirmed rename can be reverted.

### Hosting / security
- Single container (Dockerfile). Default host: **Google Cloud Run** **(default)**, scale-to-zero, secrets in Secret Manager. Alternative: run locally on the Windows PC.
- Drive access via the owner's OAuth refresh token with `drive` scope limited in practice to one folder ID; Gemini key as env var.
- SQLite file persisted (Cloud Run volume / Litestream backup to GCS), and fully rebuildable from Drive + `library.bib`.

## 3. Conventions (defaults until confirmed)

- **Filename** (confirmed by Billy): `{Year}_{Authors}_{Title}.pdf`. Authors in the order printed on the paper (Billy: "as printed always"). If there are 3 or fewer, use full surnames joined by `-`, e.g. `2024_de Lucas-Rivas-Vilarino_Multisymplectic reductions induced by polycosymplectic structures.pdf`. If there are more than 3 **(default threshold)**, use the first three letters of each surname, e.g. `2026_deLeo-Gra-Izq-Mar-Riv_From 2-covariant tensor fields to Poisson and Jacobi structures.pdf` (particle compressed to `de`+3 letters: **default**). Plain ASCII only: accents stripped, ß→ss, ø→o (Billy). Windows-sanitized, title cut at a word boundary to stay ≤ 150 chars.
- **Authors in UI**: `J. A. de León`.
- **Citation key** (from Billy's examples): one letter per author surname in printed order, then `_` and the 4-digit year (`PV_2000`, `Arn_1989`). A particle adds its lowercase initial before the surname initial (`de León` → `dL`): **default**, since `dLGIMR_2026` does this but `LRV_24` does not. Single author: first three letters of the surname (`Arn_1989`). Accents folded to ASCII. On collision append `a`, `b`.
- **BibTeX style** (from Billy's examples, see `bibtex-style.md`): authors as full `Given Surname` names joined by ` and `, in source order; title in `{{…}}`; abbreviated journal (`J. Geom. Phys.`); article volume bold `{{\bf 35}}`; pages with a single hyphen `35-55`; DOI or arXiv link goes in `note = {\href{URL}{ID}}`; optional `url` (e.g. Semantic Scholar). Preprints are `@unpublished` with `journal = {Preprint}`; work in progress is `@unpublished` with `note = {(in preparation)}`. Books carry `address, edition, isbn, publisher, series, volume`. UTF-8 accents kept.
- **Tags**: lowercase-kebab names, Gemini must pick from existing tags first and propose at most 2 new ones; colors auto-assigned from a fixed palette by hash, editable.
- **UI**: Tailwind, light/dark, HTMX for partial updates, no SPA build step.

## 4. Checklist — what's left

### Done
- [x] Plan, house style (`docs/bibtex-style.md`), project skills (`.claude/skills/`)
- [x] FastAPI app, SQLite + FTS5 (accent-insensitive), Tailwind + htmx bundled locally
- [x] `names.py`: particles, initials, citation keys, Windows-safe filenames (Billy's 4 examples as tests)
- [x] `bibtex.py`: house-style rendering per entry type
- [x] Gemini extraction with JSON schema + no-AI fallback; DOI/arXiv regex override
- [x] Storage: Drive API v3 and local-folder mode (Drive for Desktop)
- [x] Staging list, review screen with page-1 preview, live key/filename/BibTeX regeneration
- [x] Confirm & Rename (moves Inbox → library), undo, master `library.bib`
- [x] Search, tag filter (AND), add/remove tags inline, tag colors page, filtered `.bib` export
- [x] Google sign-in restricted to `OWNER_EMAIL`; sign-in also grants Drive access
- [x] Dockerfile, `.env.example`, README
- [x] Local-first on Billy's PC: `start.bat`, `config.env`, `G:/Mi unidad/Papers` (+ `Inbox`)
- [x] Minimal & fast (Billy's priority): 7 packages for the local version, ~0.6 s startup, setup skipped on later launches, inbox auto-scanned, 4 papers extracted in parallel, 1 page sent to Gemini, rare fields folded away, Ctrl+Enter to confirm
- [x] ASCII-only filenames; duplicate warning (same DOI or title); Gemini model fallback list
- [x] Pushed to github.com/AngelMrtnz/research-library; 17 tests passing

### Next
- [ ] Billy: first run of `start.bat` on the PC; rotate the Gemini key at some point
- [ ] First real run on ~10 papers; tune the Gemini prompt against real PDFs
- [ ] Bulk import of the existing library (papers already named, outside Inbox)
- [ ] Rebuild DB from `library.bib` (`python -m app.rebuild`) for backups / new machines
- [ ] Crossref/arXiv API lookup to verify Gemini output by DOI
- [ ] Settings page to edit house rules without code (threshold, particle rule)
- [ ] Batch "confirm all reviewed" on the staging list
- [x] Review page tidy-up: Delete (to trash) instead of Skip, shorter labels; LaTeX math kept in titles and BibTeX, ASCII only in filenames
- [x] Drag PDFs onto any page; one "Add PDFs" button (no Rescan/Upload); library.bib tab removed, small ".bib" download in Library
- [x] Scanned PDFs: Gemini told to read the page image when the text layer is empty or garbled

## Guiding principle
Minimal, easy and fast to run (Billy). Prefer fewer dependencies, fewer clicks, fewer visible fields.

## Open decisions

| # | Question | Options | Default |
|---|---|---|---|
| 1 | Login method | **Google** OAuth / Password | Google |
| 2 | Metadata store | **SQLite** (FTS5) / JSON | SQLite |
| 3 | Hosting | Local PC | ✅ Billy |
| 4 | Filename format | `Year_Authors_Title` | ✅ Billy |
| 5 | Multiple authors in filename | All surnames in printed order; 3-letter surnames when too many | ✅ Billy, printed order (threshold open, see 11) |
| 6 | Citation key | Surname initials, printed order, `_YYYY` (`PV_2000`, `Arn_1989`) | ✅ Billy (particle open, see 12) |
| 7 | BibTeX style | See `bibtex-style.md` | ✅ Billy |
| 8 | Where new PDFs arrive | **Inbox** subfolder / Anywhere in library | Inbox |
| 9 | Tag colors | **Auto** palette / Pick each | Auto |
| 10 | UI style | **Minimal** light+dark / Dense table / Card grid | Minimal |
| 11 | When are there "too many" authors for full surnames in the filename? | More than **3** / 4 / 5 | 3 (unconfirmed) |
| 12 | Particle in citation key | **dL** (`dLGIMR`) / L (`LRV`) | dL (unconfirmed) |
| 13 | Year in citation key | 4 digits | ✅ Billy |
| 14 | Author order inside the BibTeX entry | As printed, also in filenames and keys | ✅ Billy |
