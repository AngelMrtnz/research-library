"""Run the app in the background (pythonw, no console window) and open the browser.

Starting again restarts it, so code changes are picked up. It stops by itself a few
minutes after the last browser tab is closed. Output goes to data/server.log.
"""

import logging
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

from .config import get_settings

HOST, PORT = "127.0.0.1", 8000
URL = f"http://localhost:{PORT}/staging"
IDLE_MINUTES = 3


def running() -> bool:
    with socket.socket() as s:
        return s.connect_ex((HOST, PORT)) == 0


def stop_running() -> None:
    """Ask an instance that is already running to quit, and wait for the port to free."""
    try:
        urllib.request.urlopen(urllib.request.Request(f"http://{HOST}:{PORT}/quit",
                                                      method="POST"), timeout=5)
    except OSError:
        pass
    for _ in range(50):
        if not running():
            return
        time.sleep(0.2)


def main() -> None:
    if running():
        stop_running()
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    log = open(settings.data_dir / "server.log", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stderr = log
    logging.basicConfig(level=logging.INFO, stream=log,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "google_genai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("app").info("started on %s", URL)

    import uvicorn

    server = uvicorn.Server(uvicorn.Config("app.main:app", host=HOST, port=PORT,
                                           log_level="warning"))

    def open_when_ready() -> None:
        while not server.started:
            threading.Event().wait(0.1)
        webbrowser.open(URL)

    def stop_when_idle() -> None:
        from . import main as web

        while not server.should_exit:
            time.sleep(15)
            idle = time.monotonic() - web.last_seen
            if idle > IDLE_MINUTES * 60 and not web.busy():
                logging.getLogger("app").info("no open tabs, stopping")
                server.should_exit = True

    threading.Thread(target=open_when_ready, daemon=True).start()
    threading.Thread(target=stop_when_idle, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
