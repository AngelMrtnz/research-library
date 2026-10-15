"""Pre-flight check run by start.bat: is the library folder where .env says?"""

import sys

from .config import get_settings


def main() -> int:
    s = get_settings()
    if s.storage == "local" and not s.local_library_dir.exists():
        print(f"Library folder not found: {s.local_library_dir}")
        print("Open .env in this folder and set LOCAL_LIBRARY_DIR to your Papers folder")
        print("inside Google Drive (for example G:/My Drive/Papers).")
        return 1
    if not s.gemini_api_key:
        print("No GEMINI_API_KEY in .env: papers will be read without AI.")
    print(f"Library: {s.local_library_dir}")
    print(f"Inbox:   {s.local_inbox_dir}  (drop new PDFs here)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
