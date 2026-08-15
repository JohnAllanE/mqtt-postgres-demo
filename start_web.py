#!/usr/bin/env python3
"""Start a static server for the `web/` folder, creating/using a local venv if needed.

If a virtualenv is already active, this runs `python -m http.server` with that
interpreter. Otherwise it creates `.venv/`, installs `requirements.txt` into it,
and runs the server with the venv Python.

Usage:
  python3 start_web.py [PORT]

Defaults to port 8000.
"""
import os
import subprocess
import sys
from pathlib import Path


def in_venv() -> bool:
    if os.environ.get("VIRTUAL_ENV"):
        return True
    return getattr(sys, "base_prefix", sys.prefix) != sys.prefix


def ensure_venv(venv_path: Path) -> Path:
    python_bin = venv_path / "bin" / "python"
    if not venv_path.exists():
        print(f"Creating virtualenv at {venv_path}")
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
    if not python_bin.exists():
        raise RuntimeError(f"Expected venv python at {python_bin} not found")
    return python_bin


def install_requirements(python_exe: Path, req_file: Path):
    if not req_file.exists():
        print(f"No requirements file found at {req_file}, skipping install")
        return
    print(f"Installing requirements from {req_file} into venv...")
    subprocess.run([str(python_exe), "-m", "pip", "install", "-r", str(req_file)], check=True)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    web_dir = Path("web").resolve()
    if not web_dir.exists():
        print("Error: web/ directory not found", file=sys.stderr)
        sys.exit(2)

    if in_venv():
        print("Virtualenv active — running http.server with current Python")
        os.execv(sys.executable, [sys.executable, "-m", "http.server", str(port), "--directory", str(web_dir)])

    venv_dir = Path(".venv")
    venv_python = ensure_venv(venv_dir)
    try:
        install_requirements(venv_python, Path("requirements.txt"))
    except subprocess.CalledProcessError as e:
        print("Failed to install requirements:", e, file=sys.stderr)
        sys.exit(3)

    print(f"Launching static server for {web_dir} on port {port} inside .venv")
    os.execv(str(venv_python), [str(venv_python), "-m", "http.server", str(port), "--directory", str(web_dir)])


if __name__ == "__main__":
    main()
