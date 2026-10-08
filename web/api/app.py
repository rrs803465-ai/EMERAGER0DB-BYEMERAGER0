"""Emerager0DB web service (Railway).

Serves:
  /api/health, /api/version, /api/releases, /api/project   JSON metadata
  /get, /get.ps1                                           installer scripts
  everything else                                          static website from web/frontend

It stores no user data. Local databases never reach this service.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

BASE = Path(__file__).resolve().parent
FRONTEND_DIR = BASE.parent / "frontend"
INSTALLER_DIR = Path(os.environ.get("EMERAGER0DB_INSTALLER_DIR", BASE.parent.parent / "installer"))
RELEASES_FILE = Path(os.environ.get("EMERAGER0DB_RELEASES_FILE", BASE / "releases.json"))
REPO_URL = os.environ.get("EMERAGER0DB_REPO_URL", "https://github.com/rrs803465-ai/EMERAGER0DB-BYEMERAGER0")

INSTALLERS = {"/get": "install.sh", "/get.ps1": "install.ps1"}
MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".sh": "text/plain; charset=utf-8",
    ".ps1": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".ico": "image/x-icon",
}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
}


def load_releases() -> dict:
    return json.loads(RELEASES_FILE.read_text(encoding="utf-8"))


def api_response(path: str) -> tuple[int, object]:
    if path == "/api/health":
        return 200, {"status": "ok", "service": "emerager0db-web"}
    releases = load_releases()
    if path == "/api/version":
        return 200, {
            "latest": releases["latest"],
            "release_url": releases["release_url"],
            "downloads": releases["downloads"],
            "checksums": releases["checksums"],
        }
    if path == "/api/releases":
        return 200, releases["releases"]
    if path == "/api/project":
        return 200, {
            "name": "Emerager0DB",
            "version": releases["latest"],
            "repository": REPO_URL,
            "website": "https://falks.cyou",
            "documentation": f"{REPO_URL}/tree/main/docs",
            "license": "MIT",
        }
    return 404, {"error": "not found"}


def _inside(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "Emerager0DB-Web/0.1"
    sys_version = ""

    def do_GET(self) -> None:
        self._route(head=False)

    def do_HEAD(self) -> None:
        self._route(head=True)

    def _route(self, head: bool) -> None:
        path = unquote(urlsplit(self.path).path)
        if path.startswith("/api/"):
            try:
                status, payload = api_response(path)
            except (OSError, ValueError, KeyError):
                status, payload = 503, {"error": "release metadata unavailable"}
            body = json.dumps(payload, indent=2).encode("utf-8")
            self._send(status, body, MIME[".json"], head, {"Cache-Control": "public, max-age=300"})
            return
        if path in INSTALLERS:
            self._send_file(INSTALLER_DIR / INSTALLERS[path], head, {"Cache-Control": "public, max-age=300"})
            return
        if path in ("", "/"):
            relative = "index.html"
        elif path in ("/docs", "/docs/"):
            relative = "docs.html"
        else:
            relative = path.lstrip("/")
        self._send_file(FRONTEND_DIR / relative, head)

    def _send_file(self, target: Path, head: bool, extra: dict | None = None) -> None:
        allowed = _inside(target, FRONTEND_DIR) or _inside(target, INSTALLER_DIR)
        if not allowed or not target.is_file():
            self._send(404, b"Not found\n", MIME[".txt"], head)
            return
        ctype = MIME.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, target.read_bytes(), ctype, head, extra)

    def _send(self, status: int, body: bytes, ctype: str, head: bool, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for name, value in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(name, value)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # Keep platform logs quiet.
        return


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Emerager0DB web service listening on port {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
