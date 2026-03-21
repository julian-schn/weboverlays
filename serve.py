from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"
GIF_DIR = BASE / "components" / "gifbg" / "gifs"
HOST = "127.0.0.1"
PORT = 8080


class OverlayHandler(BaseHTTPRequestHandler):
    server_version = "StreamOverlay/1.0"

    def log_message(self, fmt: str, *args) -> None:
        if not args:
            return
        try:
            status_code = int(args[1])
        except (IndexError, TypeError, ValueError):
            status_code = None
        if status_code in (HTTPStatus.OK, HTTPStatus.NOT_MODIFIED):
            return
        super().log_message(fmt, *args)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/dashboard":
            self.send_html(BASE / "dashboard.html")
            return
        if path == "/config":
            self.send_json(load_config())
            return
        if path == "/ticker":
            self.send_html(BASE / "components" / "ticker" / "index.html")
            return
        if path == "/gifbg":
            self.send_html(BASE / "components" / "gifbg" / "index.html")
            return
        if path == "/gifbg/gifs/":
            self.send_gif_listing()
            return
        if path.startswith("/gifbg/gifs/"):
            self.send_gif(unquote(path.removeprefix("/gifbg/gifs/")))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/config":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_length = self.headers.get("Content-Length", "0")
        try:
            raw_length = int(content_length)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return

        raw_body = self.rfile.read(raw_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(HTTPStatus.BAD_REQUEST, "Body must be valid JSON")
            return

        if not isinstance(payload, dict):
            self.send_error(HTTPStatus.BAD_REQUEST, "Config root must be an object")
            return

        CONFIG_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.send_json({"ok": True})

    def send_html(self, file_path: Path) -> None:
        self.send_file(file_path, "text/html; charset=utf-8")

    def send_json(self, payload: object) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, file_path: Path, content_type: str) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_gif_listing(self) -> None:
        links = []
        for entry in sorted(GIF_DIR.iterdir(), key=lambda path: path.name.lower()):
            if entry.is_file() and entry.suffix.lower() == ".gif":
                href = f"/gifbg/gifs/{entry.name}"
                links.append(f'<a href="{href}">{entry.name}</a>')
        body = (
            "<!doctype html><html><body>"
            + "\n".join(links)
            + "</body></html>"
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_gif(self, relative_name: str) -> None:
        if not relative_name:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        candidate = (GIF_DIR / relative_name).resolve()
        try:
            candidate.relative_to(GIF_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        self.send_file(candidate, "image/gif")


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def ensure_layout() -> None:
    os.chdir(BASE)
    GIF_DIR.mkdir(parents=True, exist_ok=True)


def print_banner() -> None:
    print("── stream overlay server ─────────────────────────────")
    print(f"  dashboard       →  http://localhost:{PORT}/dashboard")
    print(f"  ticker          →  http://localhost:{PORT}/ticker")
    print(f"  gif background  →  http://localhost:{PORT}/gifbg")
    print("──────────────────────────────────────────────────────")
    print("  ctrl+c to stop")


def main() -> None:
    ensure_layout()
    server = ThreadingHTTPServer((HOST, PORT), OverlayHandler)
    print_banner()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
