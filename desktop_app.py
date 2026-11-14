from __future__ import annotations

import argparse
import ctypes
import html
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

try:
    import webview
except ModuleNotFoundError as error:
    if error.name != "webview":
        raise
    webview = None


WINDOW_TITLE = "LAVOX ELEKTRONİK | Kurumsal ERP Sistemi"
SPLASH_TITLE = "LAVOX ELEKTRONİK ERP Başlangıç"
PREFERRED_PORT = 8010
STARTUP_TIMEOUT_SECONDS = 30
MIN_SPLASH_SECONDS = 3.6
HEALTH_PATH = "/api/health"


def resource_root() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    return Path(bundled_root).resolve() if bundled_root else Path(__file__).resolve().parent


def load_desktop_translations() -> dict[str, Any]:
    locale_path = resource_root() / "locales" / "tr.json"
    with locale_path.open("r", encoding="utf-8") as locale_file:
        translations = json.load(locale_file)
    desktop_strings = translations.get("desktop")
    if not isinstance(desktop_strings, dict):
        raise ValueError("The Turkish desktop translations are incomplete.")
    splash_strings = desktop_strings.get("splash")
    if not isinstance(splash_strings, dict):
        raise ValueError("The Turkish splash screen translations are incomplete.")
    required_strings = ("title", "subtitle", "loading", "ready")
    if any(not isinstance(splash_strings.get(key), str) for key in required_strings):
        raise ValueError("The Turkish splash screen translations are incomplete.")
    statuses = splash_strings.get("statuses")
    if not isinstance(statuses, list) or not statuses or not all(
        isinstance(status, str) for status in statuses
    ):
        raise ValueError("The Turkish splash screen statuses are incomplete.")
    if not isinstance(desktop_strings.get("startup_error"), str):
        raise ValueError("The Turkish desktop error translation is incomplete.")
    return desktop_strings


def build_splash_html(desktop_strings: dict[str, Any]) -> str:
    splash = desktop_strings["splash"]
    title = html.escape(str(splash["title"]))
    subtitle = html.escape(str(splash["subtitle"]))
    loading = html.escape(str(splash["loading"]))
    statuses = json.dumps(splash["statuses"], ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; }}
    body {{ display: grid; place-items: center; color: #eef3ff; background: radial-gradient(circle at 82% 12%, rgba(86,128,235,.28), transparent 34%), linear-gradient(145deg, #0d1729, #182945); font-family: "Segoe UI", Arial, sans-serif; }}
    .splash {{ width: 100%; padding: 46px 54px 40px; }}
    .brand {{ display: flex; align-items: center; gap: 15px; }}
    .mark {{ display: grid; width: 54px; height: 54px; place-items: center; border: 1px solid rgba(164,190,255,.4); border-radius: 15px; background: linear-gradient(145deg,#5b84ed,#345dc6); box-shadow: 0 10px 24px rgba(13,44,119,.4); font-size: 30px; font-weight: 800; }}
    .title {{ margin: 0; font-size: 17px; font-weight: 750; letter-spacing: .14em; }}
    .subtitle {{ margin: 6px 0 0; color: #a7b6d0; font-size: 11px; letter-spacing: .1em; }}
    .rule {{ height: 1px; margin: 32px 0 25px; background: linear-gradient(90deg,rgba(142,170,235,.55),rgba(142,170,235,.04)); }}
    .loading {{ margin: 0 0 18px; color: #c9d4e8; font-size: 11px; }}
    .status {{ min-height: 18px; margin: 0 0 12px; color: #92a7cc; font-size: 10px; transition: opacity .25s ease; }}
    .track {{ height: 5px; overflow: hidden; border-radius: 6px; background: rgba(255,255,255,.1); }}
    .bar {{ width: 12%; height: 100%; border-radius: inherit; background: linear-gradient(90deg,#4d78e4,#86a5ff); box-shadow: 0 0 16px rgba(108,149,255,.55); transition: width .45s ease; animation: shimmer 1.5s ease-in-out infinite alternate; }}
    .footer {{ display: flex; justify-content: space-between; margin-top: 20px; color: #6f819f; font-size: 8px; letter-spacing: .04em; }}
    .splash.complete .bar {{ width: 100%; }}
    .splash.complete .status {{ color: #92dfc2; }}
    .splash.fade {{ opacity: 0; transform: translateY(-4px); transition: opacity .35s ease, transform .35s ease; }}
    @keyframes shimmer {{ from {{ filter: brightness(.9); }} to {{ filter: brightness(1.25); }} }}
  </style>
</head>
<body>
  <main class="splash" id="splash">
    <div class="brand"><div class="mark">L</div><div><h1 class="title">{title}</h1><p class="subtitle">{subtitle}</p></div></div>
    <div class="rule"></div>
    <p class="loading">{loading}</p>
    <p class="status" id="status"></p>
    <div class="track"><div class="bar" id="bar"></div></div>
    <div class="footer"><span>LAVOX ERP</span><span>BAYSÖZ YAZILIM</span></div>
  </main>
  <script>
    const statuses = {statuses};
    let statusIndex = 0;
    const statusNode = document.getElementById("status");
    const barNode = document.getElementById("bar");
    function showStatus() {{
      statusNode.style.opacity = "0";
      window.setTimeout(() => {{
        statusNode.textContent = statuses[statusIndex % statuses.length];
        statusNode.style.opacity = "1";
        statusIndex += 1;
        barNode.style.width = Math.min(20 + statusIndex * 21, 86) + "%";
      }}, 220);
    }}
    showStatus();
    window.setInterval(showStatus, 1750);
    window.finishStartup = () => {{
      document.getElementById("splash").classList.add("complete", "fade");
      statusNode.textContent = {json.dumps(str(splash["ready"]), ensure_ascii=False)};
    }};
  </script>
</body>
</html>"""


def is_lavox_health_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("status") == "ok"
        and payload.get("service") == "LAVOX Elektronik ERP"
    )


def is_lavox_server(port: int, timeout: float = 0.6) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}{HEALTH_PATH}", timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, ValueError):
        return False
    return is_lavox_health_payload(payload)


def port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class BackendRunner:
    def __init__(self) -> None:
        self._server: Any = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        if is_lavox_server(PREFERRED_PORT):
            return f"http://127.0.0.1:{PREFERRED_PORT}"

        from backend.seed_data import seed
        from backend.main import app
        import uvicorn

        seed()

        candidates: list[int] = []
        if port_is_available(PREFERRED_PORT):
            candidates.append(PREFERRED_PORT)
        candidates.extend(free_loopback_port() for _ in range(3))

        for port in candidates:
            server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    host="127.0.0.1",
                    port=port,
                    log_config=None,
                    log_level="error",
                    access_log=False,
                )
            )
            thread = threading.Thread(
                target=server.run,
                name="lavox-fastapi",
                daemon=True,
            )
            self._server = server
            self._thread = thread
            thread.start()

            deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if is_lavox_server(port):
                    return f"http://127.0.0.1:{port}"
                if not thread.is_alive():
                    break
                time.sleep(0.15)
            self._stop_candidate()

        raise RuntimeError("The local ERP backend did not become healthy.")

    def stop(self) -> None:
        self._stop_candidate()

    def _stop_candidate(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None


class DesktopBridge:
    def __init__(self, ready_callback: Any) -> None:
        self._ready_callback = ready_callback
        self._lock = threading.Lock()
        self._reported = False

    def report_ready(self) -> bool:
        with self._lock:
            if self._reported:
                return True
            self._reported = True
        self._ready_callback()
        return True


def _show_error(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, WINDOW_TITLE, 0x10)
    else:
        sys.stderr.write(message + os.linesep)


def run_desktop(icon_path: Path | None = None) -> int:
    if webview is None:
        _show_error(
            "pywebview masaüstü bileşeni bulunamadı. "
            "Onaylı masaüstü bağımlılıkları bu bilgisayara yüklenmelidir."
        )
        return 2

    try:
        desktop_strings = load_desktop_translations()
    except (OSError, ValueError, KeyError):
        _show_error("Türkçe masaüstü başlangıç kaynakları yüklenemedi.")
        return 1
    startup_error = str(desktop_strings["startup_error"])
    backend = BackendRunner()
    ready_event = threading.Event()
    startup_started_at = time.monotonic()
    boot_lock = threading.Lock()
    boot_started = False
    transition_lock = threading.Lock()
    transition_started = False

    splash_window: Any = None
    main_window: Any = None

    def finish_transition() -> None:
        nonlocal transition_started
        with transition_lock:
            if transition_started:
                return
            transition_started = True

        def show_main_window() -> None:
            main_window.show()
            splash_window.destroy()

        def finish_splash() -> None:
            splash_window.evaluate_js("window.finishStartup()")
            threading.Timer(0.4, show_main_window).start()

        remaining = max(MIN_SPLASH_SECONDS - (time.monotonic() - startup_started_at), 0)
        threading.Timer(remaining, finish_splash).start()

    bridge = DesktopBridge(lambda: (ready_event.set(), finish_transition()))
    def boot_backend() -> None:
        nonlocal boot_started
        with boot_lock:
            if boot_started:
                return
            boot_started = True
        try:
            url = backend.start()
            main_window.load_url(url)
            if not ready_event.wait(STARTUP_TIMEOUT_SECONDS):
                raise RuntimeError("The Turkish ERP interface did not finish loading.")
        except Exception:
            splash_window.destroy()
            main_window.destroy()
            _show_error(startup_error)
            backend.stop()

    try:
        splash_window = webview.create_window(
            title=SPLASH_TITLE,
            html=build_splash_html(desktop_strings),
            width=590,
            height=330,
            resizable=False,
            frameless=True,
            easy_drag=True,
            shadow=True,
            on_top=True,
        )
        main_window = webview.create_window(
            title=WINDOW_TITLE,
            url="about:blank",
            width=1440,
            height=900,
            min_size=(1024, 720),
            resizable=True,
            maximized=True,
            hidden=True,
            js_api=bridge,
        )
        splash_window.events.shown += lambda: threading.Thread(
            target=boot_backend,
            name="lavox-startup",
            daemon=True,
        ).start()
        webview.start(
            debug=False,
            gui="edgechromium",
            private_mode=True,
            icon=os.fspath(icon_path) if icon_path else None,
        )
    except Exception:
        if splash_window is not None:
            splash_window.destroy()
        if main_window is not None:
            main_window.destroy()
        _show_error(startup_error)
        return 1
    finally:
        backend.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the LAVOX native Windows desktop app.")
    parser.add_argument("--icon", type=Path, help="Optional Windows .ico file for the app window.")
    arguments = parser.parse_args(argv)
    icon_path = arguments.icon
    if icon_path is None:
        assets = resource_root() / "assets"
        default_icon = assets / "lavox.ico"
        packaged_icons = sorted(assets.glob("*.ico")) if assets.is_dir() else []
        icon_path = default_icon if default_icon.is_file() else (
            packaged_icons[0] if packaged_icons else None
        )
    elif icon_path.suffix.lower() != ".ico" or not icon_path.is_file():
        parser.error("--icon must point to an existing .ico file")
    return run_desktop(icon_path)


if __name__ == "__main__":
    raise SystemExit(main())
