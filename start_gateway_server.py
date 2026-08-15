#!/usr/bin/env python3
"""Start the gateway server (TCP->WebSocket), creating/using a local venv if needed.

If a virtualenv is active, this will run `gateway/server.py` with the current Python.
Otherwise it will create `.venv/`, install `requirements.txt`, and execute the server
using the venv Python.

Usage:
  python3 start_gateway_server.py [--] [args...]

Any additional positional args are forwarded to `gateway/server.py`.
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
    forward_args = sys.argv[1:]
    if forward_args and forward_args[0] == "--":
        forward_args = forward_args[1:]

    server_script = Path("gateway") / "server.py"
    if not server_script.exists():
        print("Error: gateway/server.py not found", file=sys.stderr)
        sys.exit(2)

    if in_venv():
        print("Virtualenv active — running gateway server with current Python")
        os.execv(sys.executable, [sys.executable, str(server_script), *forward_args])

    venv_dir = Path(".venv")
    venv_python = ensure_venv(venv_dir)
    try:
        install_requirements(venv_python, Path("requirements.txt"))
    except subprocess.CalledProcessError as e:
        print("Failed to install requirements:", e, file=sys.stderr)
        sys.exit(3)

    print("Launching gateway server inside .venv")
    os.execv(str(venv_python), [str(venv_python), str(server_script), *forward_args])


if __name__ == "__main__":
    main()
