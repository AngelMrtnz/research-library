# Research Library

A private web app that classifies academic PDFs in Google Drive, lets you review the proposed metadata, and only then renames the file and adds it to a master `library.bib`.

- **Inbox → Review → Confirm & Rename.** Nothing is renamed automatically.
- Gemini proposes title, authors (in printed order, with particles like *de León*), year, type, journal, DOI/arXiv, tags and a BibTeX entry in your house style. Without a Gemini key it falls back to PDF metadata and the first page, so you can try it for free.
- Files become `2000_Pugliese-Vinogradov_On the geometry of singular Lagrangians.pdf`, safe in Windows Explorer.
- Instant accent-insensitive search (`vilarino` finds *Vilariño*) across title, authors, year, citation key and tags. Clickable, color-coded tags. Export any filtered set as `.bib`.

## Try it locally (5 minutes, no Google setup)

```bash
pip install -r requirements.txt
AUTH_DISABLED=1 uvicorn app.main:app --reload
```
Put some PDFs in `data/library/Inbox/` and open http://localhost:8000/staging. New PDFs are picked up automatically.

On Windows PowerShell:
```powershell
$env:AUTH_DISABLED=1; uvicorn app.main:app --reload
```

## Use it with your Google Drive

**Option A: on your own PC (simplest, the default).** Double-click `start.bat`: it opens the browser and keeps running in the background with no window (log in `data/server.log`); double-clicking it again restarts it (picking up any code changes), and it stops by itself a few minutes after you close the last tab, or click **Quit**. The first run creates `config.env` from `config.env.example`; set `LOCAL_LIBRARY_DIR` to your Papers folder inside Google Drive for Desktop and paste your `GEMINI_API_KEY`. Renames happen on disk and Drive syncs them. The app listens on `127.0.0.1` only, so there is no login.

**Option B: hosted (reach it from any device).** Uses the Drive API and needs the extra packages in `requirements-hosted.txt`.
1. In [Google Cloud console](https://console.cloud.google.com/): create a project, enable the **Google Drive API**, configure the OAuth consent screen (External, add yourself as a test user), and create an **OAuth client ID** of type *Web application* with redirect URI `https://<your-host>/auth/callback`.
2. Get a Gemini key at https://aistudio.google.com/apikey.
3. In Drive, create `Papers/` and `Papers/Inbox/`; copy each folder's ID from its URL.
4. Copy `.env.example` to `.env` and fill it in (`STORAGE=gdrive`, `AUTH_DISABLED` unset).
5. Deploy the container, e.g. Cloud Run:
   ```bash
   gcloud run deploy research-library --source . --region europe-west1 \
     --env-vars-file env.yaml --add-volume name=data,type=cloud-storage,bucket=<bucket> \
     --add-volume-mount volume=data,mount-path=/data --max-instances 1
   ```
6. Open the app and sign in with `OWNER_EMAIL`. That sign-in also grants Drive access; the token is stored in `/data`.

Only `OWNER_EMAIL` can sign in. Everything else gets a 403.

## Day to day
1. Drop PDFs into `Papers/Inbox` (or use **Upload** on the Review page).
2. Open **Review**. New PDFs are picked up automatically and read in parallel (a few seconds each with Gemini).
3. Open one: first page on the left, every field editable on the right. Changing title/authors/year/type regenerates the key, filename and BibTeX live; you can still hand-edit the BibTeX.
4. **Confirm & Rename** (or Ctrl+Enter) renames the file, moves it from `Inbox/` to `Papers/`, and rewrites `Papers/library.bib`. **Undo rename** puts it back. **Delete** moves the PDF to `Papers/_Deleted`, so you can always get it back.

## Development
```bash
pip install -r requirements-dev.txt
pytest -q && ruff check .
```
See `PLAN.md` for decisions and the checklist, `docs/bibtex-style.md` for the house style, and `.claude/skills/` for the Claude skills that build and run this.
