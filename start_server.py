#!/usr/bin/env python3
"""Start the server bridge (TCP->WebSocket), creating/using a local venv if needed.

This mirrors other `start_*` helpers but runs the server-side bridge located at
`server/server.py`.
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
    # helper options: allow skipping starting ingest/api services
    no_ingest = False
    no_api = False
    if "--no-ingest" in forward_args:
        no_ingest = True
        forward_args = [a for a in forward_args if a != "--no-ingest"]
    if "--no-api" in forward_args:
        no_api = True
        forward_args = [a for a in forward_args if a != "--no-api"]

    server_script = Path("server") / "server.py"
    if not server_script.exists():
        print("Error: server/server.py not found", file=sys.stderr)
        sys.exit(2)

    if in_venv():
        print("Virtualenv active — running server with current Python")
        # start ingest in background (use current Python)
        if not no_ingest:
            ingest_script = Path("server") / "ingest.py"
            if ingest_script.exists():
                print(f"Starting ingest service in background: {ingest_script}")
                subprocess.Popen([sys.executable, str(ingest_script)], stdout=None, stderr=None)
        if not no_api:
            api_script = Path("server") / "api.py"
            if api_script.exists():
                print(f"Starting API service in background: {api_script}")
                subprocess.Popen([sys.executable, str(api_script)], stdout=None, stderr=None)
        os.execv(sys.executable, [sys.executable, str(server_script), *forward_args])

    venv_dir = Path(".venv")
    venv_python = ensure_venv(venv_dir)
    try:
        install_requirements(venv_python, Path("requirements.txt"))
    except subprocess.CalledProcessError as e:
        print("Failed to install requirements:", e, file=sys.stderr)
        sys.exit(3)

    print("Launching server inside .venv")
    # start ingest inside venv in background unless user opted out
    ingest_script = Path("server") / "ingest.py"
    if not no_ingest and ingest_script.exists():
        print(f"Starting ingest service in background inside .venv: {ingest_script}")
        subprocess.Popen([str(venv_python), str(ingest_script)], stdout=None, stderr=None)
    api_script = Path("server") / "api.py"
    if not no_api and api_script.exists():
        print(f"Starting API service in background inside .venv: {api_script}")
        subprocess.Popen([str(venv_python), str(api_script)], stdout=None, stderr=None)

    os.execv(str(venv_python), [str(venv_python), str(server_script), *forward_args])


if __name__ == "__main__":
    main()
