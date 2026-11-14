from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def build_command(icon_path: Path | None = None) -> list[str]:
    if sys.platform != "win32":
        raise RuntimeError("The standalone Windows executable must be built on Windows.")
    if importlib.util.find_spec("PyInstaller") is None:
        raise RuntimeError(
            "PyInstaller is missing. Install the approved desktop requirements before building."
        )
    if importlib.util.find_spec("webview") is None:
        raise RuntimeError(
            "pywebview is missing. Install the approved desktop requirements before building."
        )
    if icon_path is None:
        default_icon = PROJECT_ROOT / "assets" / "lavox.ico"
        icon_path = default_icon if default_icon.is_file() else None

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--noconsole",
        "--name",
        "LAVOX_Elektronik_ERP",
        "--add-data",
        f"{PROJECT_ROOT / 'frontend'}{os.pathsep}frontend",
        "--add-data",
        f"{PROJECT_ROOT / 'locales'}{os.pathsep}locales",
        "--collect-all",
        "webview",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.lifespan.on",
        str(PROJECT_ROOT / "desktop_app.py"),
    ]
    if icon_path is not None:
        command[7:7] = ["--icon", str(icon_path)]
        command[-1:-1] = ["--add-data", f"{icon_path}{os.pathsep}assets"]
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the standalone LAVOX Windows application.")
    parser.add_argument("--icon", type=Path, help="Optional .ico file embedded in the executable.")
    arguments = parser.parse_args(argv)
    icon_path = arguments.icon
    if icon_path is not None:
        icon_path = icon_path.resolve()
        if icon_path.suffix.lower() != ".ico" or not icon_path.is_file():
            parser.error("--icon must point to an existing .ico file")
    else:
        default_icon = PROJECT_ROOT / "assets" / "lavox.ico"
        icon_path = default_icon if default_icon.is_file() else None

    try:
        command = build_command(icon_path)
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
