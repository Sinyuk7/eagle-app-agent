#!/usr/bin/env python3
"""Serve a moodboard project directory on localhost for browser QA."""

import argparse
import functools
import http.server
import json
import os
import socket
import socketserver
import subprocess
import sys
from pathlib import Path


def choose_port(host: str, preferred: int = 0) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, preferred))
        return sock.getsockname()[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", help="Project directory containing index.html")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument(
        "--port", type=int, default=0, help="Preferred port; 0 chooses automatically"
    )
    parser.add_argument(
        "--preflight-localhost",
        action="store_true",
        help="Run check_html.py --localhost-mode before serving and refuse unsafe file:// or absolute local asset refs",
    )
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).expanduser().resolve()
    index_path = project_dir / "index.html"
    if not index_path.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "missing_index",
                    "project_dir": str(project_dir),
                    "index_html": str(index_path),
                },
                ensure_ascii=False,
            )
        )
        return 2

    if args.preflight_localhost:
        checker = Path(__file__).resolve().parent / "check_html.py"
        cmd = [
            sys.executable,
            str(checker),
            str(index_path),
            "--check-assets",
            "--check-links",
            "--localhost-mode",
        ]
        result = subprocess.run(cmd, text=True, capture_output=True)
        if result.returncode != 0:
            try:
                payload = json.loads(result.stdout)
            except Exception:
                payload = {"stdout": result.stdout, "stderr": result.stderr}
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "localhost_preflight_failed",
                        "project_dir": str(project_dir),
                        "index_html": str(index_path),
                        "check": payload,
                    },
                    ensure_ascii=False,
                )
            )
            return 3

    port = choose_port(args.host, args.port)
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(project_dir)
    )

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer((args.host, port), handler) as httpd:
        print(
            json.dumps(
                {
                    "ok": True,
                    "url": f"http://{args.host}:{port}/index.html",
                    "pid": os.getpid(),
                    "project_dir": str(project_dir),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
