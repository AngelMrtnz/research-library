from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Who may sign in. Only this Google account gets past the login.
    owner_email: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    session_secret: str = "change-me"
    # Local development only: skip login entirely.
    auth_disabled: bool = False

    # "gdrive" uses the Drive API; "local" works on a folder on disk, e.g. the
    # Google Drive for Desktop folder (G:\My Drive\Papers) on your own PC.
    storage: str = "gdrive"
    drive_library_folder_id: str = ""
    drive_inbox_folder_id: str = ""
    local_library_dir: Path = Path("data/library")
    local_inbox_dir: Path = Path("data/library/Inbox")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    data_dir: Path = Path("data")
    bib_filename: str = "library.bib"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "library.sqlite3"

    @property
    def drive_token_path(self) -> Path:
        return self.data_dir / "drive_token.json"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


@lru_cache
def get_settings() -> Settings:
    return Settings()
