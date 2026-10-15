"""Run the app in the background (pythonw, no console window) and open the browser.

If it is already running, only the browser opens. Output goes to data/server.log.
"""

import socket
import sys
import threading
import webbrowser

from .config import get_settings

HOST, PORT = "127.0.0.1", 8000
URL = f"http://localhost:{PORT}/staging"


def running() -> bool:
    with socket.socket() as s:
        return s.connect_ex((HOST, PORT)) == 0


def main() -> None:
    if running():
        webbrowser.open(URL)
        return
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    log = open(settings.data_dir / "server.log", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stderr = log

    import uvicorn

    server = uvicorn.Server(uvicorn.Config("app.main:app", host=HOST, port=PORT,
                                           log_level="warning"))

    def open_when_ready() -> None:
        while not server.started:
            threading.Event().wait(0.1)
        webbrowser.open(URL)

    threading.Thread(target=open_when_ready, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
