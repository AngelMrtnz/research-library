"""File storage: Google Drive API, or a local folder.

Files are always addressed by a stable id, never by name, so renames are safe.
Nothing here is called during ingestion except list/download; renames and the
library.bib upload happen only from the confirm handler.
"""

from __future__ import annotations

import io
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Settings

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


@dataclass
class StoredFile:
    id: str
    name: str


class Storage(Protocol):
    def list_new_pdfs(self) -> list[StoredFile]: ...
    def list_library_names(self) -> set[str]: ...
    def download(self, file_id: str) -> bytes: ...
    def rename(self, file_id: str, new_name: str, to_library: bool) -> None: ...
    def write_bib(self, text: str) -> None: ...
    def save_upload(self, name: str, data: bytes) -> StoredFile: ...
    def view_url(self, file_id: str) -> str | None: ...


class LocalStorage:
    """A folder on disk. On your PC, point it at the Drive for Desktop folder."""

    def __init__(self, library: Path, inbox: Path, bib_name: str, index_path: Path):
        self.library, self.inbox, self.bib_name = library, inbox, bib_name
        self.index_path = index_path
        library.mkdir(parents=True, exist_ok=True)
        inbox.mkdir(parents=True, exist_ok=True)
        self.index: dict[str, str] = (
            json.loads(index_path.read_text()) if index_path.exists() else {}
        )

    def _save(self) -> None:
        self.index_path.write_text(json.dumps(self.index, indent=1))

    def _path(self, file_id: str) -> Path:
        return Path(self.index[file_id])

    def _register(self, path: Path) -> StoredFile:
        known = {v: k for k, v in self.index.items()}
        fid = known.get(str(path))
        if fid is None:
            fid = uuid.uuid4().hex
            self.index[fid] = str(path)
            self._save()
        return StoredFile(fid, path.name)

    def list_new_pdfs(self) -> list[StoredFile]:
        return [self._register(p) for p in sorted(self.inbox.glob("*.pdf"))]

    def list_library_names(self) -> set[str]:
        return {p.name for p in self.library.glob("*.pdf")}

    def download(self, file_id: str) -> bytes:
        return self._path(file_id).read_bytes()

    def rename(self, file_id: str, new_name: str, to_library: bool) -> None:
        src = self._path(file_id)
        dest = (self.library if to_library else self.inbox) / new_name
        if dest.exists() and dest != src:
            raise FileExistsError(dest.name)
        src.rename(dest)
        self.index[file_id] = str(dest)
        self._save()

    def write_bib(self, text: str) -> None:
        (self.library / self.bib_name).write_text(text, encoding="utf-8")

    def save_upload(self, name: str, data: bytes) -> StoredFile:
        path = self.inbox / Path(name).name
        n = 2
        while path.exists():
            path = self.inbox / f"{Path(name).stem} ({n}).pdf"
            n += 1
        path.write_bytes(data)
        return self._register(path)

    def view_url(self, file_id: str) -> str | None:
        return None


class DriveStorage:
    """Google Drive API v3 with the owner's OAuth token."""

    def __init__(self, settings: Settings):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token = settings.drive_token_path
        if not token.exists():
            raise RuntimeError("Sign in once to grant Drive access.")
        creds = Credentials.from_authorized_user_file(str(token), DRIVE_SCOPES)
        self.svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.library_id = settings.drive_library_folder_id
        self.inbox_id = settings.drive_inbox_folder_id or settings.drive_library_folder_id
        self.bib_name = settings.bib_filename

    def _list(self, folder: str, extra: str = "") -> list[dict]:
        q = f"'{folder}' in parents and trashed = false {extra}"
        out, token = [], None
        while True:
            res = self.svc.files().list(
                q=q, fields="nextPageToken, files(id, name)", pageSize=1000,
                pageToken=token, supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            out += res.get("files", [])
            token = res.get("nextPageToken")
            if not token:
                return out

    def list_new_pdfs(self) -> list[StoredFile]:
        files = self._list(self.inbox_id, "and mimeType = 'application/pdf'")
        return [StoredFile(f["id"], f["name"]) for f in files]

    def list_library_names(self) -> set[str]:
        return {f["name"] for f in self._list(self.library_id)}

    def download(self, file_id: str) -> bytes:
        from googleapiclient.http import MediaIoBaseDownload

        buf = io.BytesIO()
        req = self.svc.files().get_media(fileId=file_id, supportsAllDrives=True)
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue()

    def rename(self, file_id: str, new_name: str, to_library: bool) -> None:
        meta = self.svc.files().get(fileId=file_id, fields="parents",
                                    supportsAllDrives=True).execute()
        parents = meta.get("parents", [])
        target = self.library_id if to_library else self.inbox_id
        kwargs = {}
        if target not in parents:
            kwargs = {"addParents": target, "removeParents": ",".join(parents)}
        self.svc.files().update(fileId=file_id, body={"name": new_name},
                                supportsAllDrives=True, **kwargs).execute()

    def write_bib(self, text: str) -> None:
        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(text.encode()), mimetype="text/plain")
        existing = self._list(self.library_id, f"and name = '{self.bib_name}'")
        if existing:
            self.svc.files().update(fileId=existing[0]["id"], media_body=media,
                                    supportsAllDrives=True).execute()
        else:
            self.svc.files().create(
                body={"name": self.bib_name, "parents": [self.library_id]},
                media_body=media, supportsAllDrives=True,
            ).execute()

    def save_upload(self, name: str, data: bytes) -> StoredFile:
        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/pdf")
        f = self.svc.files().create(
            body={"name": Path(name).name, "parents": [self.inbox_id]},
            media_body=media, fields="id, name", supportsAllDrives=True,
        ).execute()
        return StoredFile(f["id"], f["name"])

    def view_url(self, file_id: str) -> str | None:
        return f"https://drive.google.com/file/d/{file_id}/view"


def make_storage(settings: Settings) -> Storage:
    if settings.storage == "local":
        return LocalStorage(settings.local_library_dir, settings.local_inbox_dir,
                            settings.bib_filename, settings.data_dir / "local_index.json")
    return DriveStorage(settings)
