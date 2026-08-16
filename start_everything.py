#!/usr/bin/env python3
"""Start the server, gateway, and web UI together in the background.

This is a convenience wrapper for resetting the system in one terminal. It
launches the existing `start_server.py`, `start_gateway.py`, and `start_web.py`
helpers as background processes so you can keep one quiet window open while the
services run.

Usage:
  python3 start_everything.py
  python3 start_everything.py --quiet
  python3 start_everything.py --web-port 8001

By default this script suppresses child stdout/stderr so the terminal stays
quiet. Use `--verbose` to keep the child output visible.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def spawn(command: list[str], quiet: bool, cwd: Path):
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.DEVNULL if quiet else None
    return subprocess.Popen(
        command,
        stdout=stdout,
        stderr=stderr,
        cwd=str(cwd),
        start_new_session=True,
    )


def stop_process(proc: subprocess.Popen, name: str):
    if proc.poll() is not None:
        return
    print(f"Stopping {name} process group (pgid {proc.pid})...")
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(f"{name} did not exit in time; killing process group {proc.pid}")
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        proc.wait(timeout=5)


def stop_all(processes: list[tuple[str, subprocess.Popen]]):
    for name, proc in reversed(processes):
        stop_process(proc, name)


def main():
    parser = argparse.ArgumentParser(description='Start the full demo stack in the background')
    parser.add_argument('--web-port', type=int, default=8000, help='Port for the static web server (default: 8000)')
    parser.add_argument('--verbose', action='store_true', help='Show child output instead of suppressing it')
    args = parser.parse_args()

    quiet = not args.verbose
    repo_root = Path(__file__).resolve().parent

    server_script = repo_root / 'start_server.py'
    gateway_script = repo_root / 'start_gateway.py'
    web_script = repo_root / 'start_web.py'

    missing = [str(path.name) for path in (server_script, gateway_script, web_script) if not path.exists()]
    if missing:
        print(f"Missing launcher script(s): {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)

    print('Starting server, gateway, and web UI in the background...')
    processes = [
        ('server', spawn([sys.executable, str(server_script)], quiet, repo_root)),
        ('gateway', spawn([sys.executable, str(gateway_script)], quiet, repo_root)),
        ('web', spawn([sys.executable, str(web_script), str(args.web_port)], quiet, repo_root)),
    ]

    for name, proc in processes:
        if proc.poll() is not None:
            print(f"{name} exited immediately with code {proc.returncode}", file=sys.stderr)
            sys.exit(proc.returncode or 1)

    print(f"Started: {', '.join(name for name, _ in processes)}")
    print(f"Web UI should be available at http://localhost:{args.web_port}")
    print('Use the individual start_* scripts if you want separate debug windows.')

    shutting_down = False

    def request_shutdown(_signum=None, _frame=None):
        nonlocal shutting_down
        shutting_down = True

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    try:
        while not shutting_down:
            exited = []
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    exited.append((name, code))
            for name, code in exited:
                print(f"{name} exited with code {code}; the supervisor will stay open until Ctrl-C")
                processes = [(n, p) for n, p in processes if n != name]
            if not processes:
                print('No child processes remain; waiting for Ctrl-C to exit the supervisor')
            time.sleep(1)
    finally:
        stop_all(processes)
        print('All child processes stopped')


if __name__ == '__main__':
    main()