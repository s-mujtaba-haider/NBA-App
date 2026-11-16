"""Baseline desktop app: a native window around the same web app, with the engine running locally.

Start:  python desktop/launcher.py        (from source)   or   Baseline.exe   (installed)

1. License. When LICENSE_SERVER_URL is set (the owner's hosted server), the app needs a valid signed license:
   the stored token is verified with the bundled public key and refreshed online; without one, an activation
   window asks for email + license key. Without LICENSE_SERVER_URL (developer copy) this step is skipped.
2. The API and engine start in-process on a free localhost port. Writable data lives in %APPDATA%/Baseline.
3. The window opens on the app. Closing it stops everything.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    HOME = Path(os.getenv("APPDATA") or Path.home()) / "Baseline"
    os.environ.setdefault("BASELINE_HOME", str(HOME))
    exe_env = Path(sys.executable).parent / ".env"       # settings next to the exe (installer writes it)
    if exe_env.exists():
        from dotenv import load_dotenv
        load_dotenv(exe_env)
else:
    ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "desktop"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
log = logging.getLogger("desktop")
TITLE = "Baseline · NBA"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int) -> None:
    import uvicorn
    from backend.app.main import app
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    threading.Thread(target=uvicorn.Server(cfg).run, daemon=True, name="api").start()
    for _ in range(200):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("The local server did not start")


ACTIVATE_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;height:100vh;display:grid;place-items:center;background:#07080a;color:#eef1f4;font:14px system-ui,sans-serif}
.c{width:340px}h1{font:800 44px/0.9 'Arial Narrow',system-ui;text-transform:uppercase;margin:0 0 24px}h1 b{color:#c8f560}
label{display:block;font:10.5px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;color:#6b7480;margin:14px 0 6px}
input{width:100%;box-sizing:border-box;height:40px;border-radius:5px;border:1px solid #1d2228;background:#0c0e11;color:#eef1f4;padding:0 12px;font:14px ui-monospace,monospace}
button{margin-top:20px;width:100%;height:40px;border:0;border-radius:5px;background:#c8f560;color:#07080a;font-weight:600;cursor:pointer}
#e{color:#ff5470;font-size:12px;margin-top:12px;min-height:16px}
</style></head><body><div class="c"><h1>Activate <b>Baseline</b></h1><p style="color:#6b7480;font-size:12px">MSG</p>
<label>Email</label><input id="i" value="IDENT"><label>License key</label><input id="k" placeholder="XXXX-XXXX-XXXX-XXXX-XXXX">
<button onclick="go()">Activate</button><div id="e"></div></div><script>
async function go(){document.getElementById('e').textContent='Checking…';
const r=await pywebview.api.activate(document.getElementById('i').value,document.getElementById('k').value.toUpperCase());
document.getElementById('e').textContent=r.ok?'':r.message}</script></body></html>"""


class ActivationApi:
    """Called from the activation page; on success the same window switches to the app."""

    def __init__(self, on_ok):
        self.window = None
        self.on_ok = on_ok

    def activate(self, ident: str, key: str):
        import activation
        ok, _, msg = activation.activate_online(ident.strip(), key.strip())
        if ok:
            self.window.load_url(self.on_ok())
        return {"ok": ok, "message": msg}


def needs_activation() -> str | None:
    """None when the app may start; otherwise the message to show on the activation page."""
    if not os.getenv("LICENSE_SERVER_URL"):
        log.info("LICENSE_SERVER_URL not set: developer copy, license check skipped")
        return None
    import activation
    ok, _, msg = activation.check_startup()
    log.info("License: %s", msg)
    return None if ok else msg


def main() -> None:
    try:
        import webview
    except ImportError:
        webview = None
    state = {}

    def boot() -> str:
        if "url" not in state:
            port = free_port()
            start_server(port)
            state["url"] = f"http://127.0.0.1:{port}/"
            log.info("Baseline running at %s", state["url"])
        return state["url"]

    msg = needs_activation()
    if webview is None:                                   # no native window available: use the browser
        if msg is not None:
            raise SystemExit(f"License required: {msg}")
        import webbrowser
        webbrowser.open(boot())
        while True:
            time.sleep(3600)
    opts = dict(width=1440, height=920, min_size=(1024, 680), background_color="#07080A")
    if msg is None:
        webview.create_window(TITLE, boot(), **opts)
    else:
        import activation
        api = ActivationApi(boot)
        ident, _ = activation.stored_credentials()
        html = ACTIVATE_HTML.replace("MSG", json.dumps(msg)[1:-1]).replace("IDENT", ident or "")
        api.window = webview.create_window(TITLE, html=html, js_api=api, **opts)
    webview.start()


if __name__ == "__main__":
    main()
