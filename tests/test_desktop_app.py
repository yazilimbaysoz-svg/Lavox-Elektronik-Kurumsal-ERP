from __future__ import annotations

import json
import os
import runpy
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

from build_exe import build_command
from desktop_app import (
    BackendRunner,
    build_splash_html,
    is_lavox_server,
    load_desktop_translations,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HealthHandler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {}

    def do_GET(self) -> None:
        body = json.dumps(self.payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class DesktopStartupTests(unittest.TestCase):
    def test_splash_contains_translated_sequential_statuses(self) -> None:
        translations = load_desktop_translations()
        splash = translations["splash"]
        html = build_splash_html(translations)
        statuses = splash["statuses"]
        positions = [html.index(status) for status in statuses]

        self.assertEqual(positions, sorted(positions))
        self.assertIn("LAVOX ELEKTRONİK", html)
        self.assertIn("Kurumsal ERP v2.0", html)
        self.assertIn("window.finishStartup", html)

    def test_backend_reuses_only_a_matching_lavox_health_response(self) -> None:
        HealthHandler.payload = {
            "status": "ok",
            "service": "LAVOX Elektronik ERP",
        }
        server = HTTPServer(("127.0.0.1", 0), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertTrue(is_lavox_server(server.server_port))
            HealthHandler.payload = {"status": "ok", "service": "Other service"}
            self.assertFalse(is_lavox_server(server.server_port))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_backend_falls_back_when_preferred_port_is_occupied(self) -> None:
        class FakeServer:
            should_exit = False

            def __init__(self, _config: Any) -> None:
                self.config = _config

            def run(self) -> None:
                self.should_exit = True

        runner = BackendRunner()
        with (
            patch("desktop_app.is_lavox_server", side_effect=lambda port: port == 9142),
            patch("desktop_app.port_is_available", return_value=False),
            patch("desktop_app.free_loopback_port", return_value=9142),
            patch("uvicorn.Server", FakeServer),
        ):
            self.assertEqual(runner.start(), "http://127.0.0.1:9142")
        runner.stop()

    def test_frozen_database_uses_writable_user_data_outside_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as user_data, tempfile.TemporaryDirectory() as bundle:
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", bundle, create=True),
                patch.dict(os.environ, {"LOCALAPPDATA": user_data}),
            ):
                settings = runpy.run_path(str(PROJECT_ROOT / "backend" / "database.py"))

        self.assertEqual(settings["PROJECT_ROOT"], Path(bundle).resolve())
        self.assertEqual(
            settings["DATABASE_PATH"],
            Path(user_data) / "Lavox Elektronik ERP" / "data" / "lavox_enterprise.db",
        )

    def test_native_launcher_database_root_uses_configured_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as user_data:
            with patch.dict(os.environ, {"LAVOX_DATA_ROOT": user_data}):
                settings = runpy.run_path(str(PROJECT_ROOT / "backend" / "database.py"))

        self.assertEqual(settings["DATA_ROOT"], Path(user_data).resolve())
        self.assertEqual(
            settings["DATABASE_PATH"],
            settings["DATA_ROOT"] / "data" / "lavox_enterprise.db",
        )

    def test_build_command_is_single_file_silent_and_embeds_ui_assets(self) -> None:
        with (
            patch("build_exe.sys.platform", "win32"),
            patch("build_exe.importlib.util.find_spec", return_value=object()),
        ):
            command = build_command()

        self.assertIn("--onefile", command)
        self.assertIn("--noconsole", command)
        self.assertIn("--icon", command)
        self.assertTrue(any("frontend" in item for item in command))
        self.assertTrue(any("locales" in item for item in command))


if __name__ == "__main__":
    unittest.main()
