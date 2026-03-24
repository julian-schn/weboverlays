from __future__ import annotations

import base64
import json
import os
import time
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, unquote, urlparse
from urllib.request import Request, urlopen


BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"
GIF_DIR = BASE / "components" / "gifbg" / "gifs"
HOST = "127.0.0.1"
PORT = 8080
SPOTIFY_REDIRECT_URI = f"http://localhost:{PORT}/spotify/callback"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_CURRENT_TRACK_URL = "https://api.spotify.com/v1/me/player/currently-playing"


class OverlayHandler(BaseHTTPRequestHandler):
    server_version = "StreamOverlay/1.0"

    def log_message(self, fmt: str, *args) -> None:
        if not args:
            return
        try:
            status_code = int(args[1])
        except (IndexError, TypeError, ValueError):
            status_code = None
        if status_code in (HTTPStatus.OK, HTTPStatus.NOT_MODIFIED, HTTPStatus.NO_CONTENT):
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
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/dashboard":
            self.send_html(BASE / "dashboard.html")
            return
        if path == "/config":
            self.send_json(get_public_config())
            return
        if path == "/ticker":
            self.send_html(BASE / "components" / "ticker" / "index.html")
            return
        if path == "/gifbg":
            self.send_html(BASE / "components" / "gifbg" / "index.html")
            return
        if path == "/spotify":
            self.send_html(BASE / "components" / "spotify" / "index.html")
            return
        if path == "/spotify/callback":
            self.handle_spotify_callback(parsed)
            return
        if path == "/spotify/now-playing":
            self.handle_spotify_now_playing()
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

        current = load_config()
        save_config(merge_dashboard_payload(current, payload))
        self.send_json({"ok": True})

    def handle_spotify_callback(self, parsed) -> None:
        code = parse_qs(parsed.query).get("code", [""])[0]
        if not code:
            self.send_html_text(
                "missing authorization code. you can close this tab.",
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        config = load_config()
        spotify = config.setdefault("spotify", {})
        client_id = spotify.get("clientId", "")
        client_secret = spotify.get("clientSecret", "")

        if not client_id or not client_secret:
            self.send_html_text(
                "spotify credentials are missing. save them in the dashboard first.",
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            token_payload = spotify_token_request(
                client_id,
                client_secret,
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": SPOTIFY_REDIRECT_URI,
                },
            )
        except SpotifyAuthError as error:
            self.send_html_text(str(error), status=HTTPStatus.BAD_GATEWAY)
            return

        apply_spotify_token_payload(spotify, token_payload)
        save_config(config)
        self.send_html_text("authorized. you can close this tab.")

    def handle_spotify_now_playing(self) -> None:
        config = load_config()
        spotify = config.get("spotify", {})
        access_token = spotify.get("accessToken", "")
        expires_at = int(spotify.get("tokenExpiresAt", 0) or 0)
        now_ms = int(time.time() * 1000)

        if not access_token:
            self.send_json({"error": "unauthorized"})
            return

        if expires_at - now_ms < 60000:
            try:
                refresh_spotify_access_token(config)
            except SpotifyAuthError:
                self.send_json({"error": "unauthorized"})
                return
            spotify = config.get("spotify", {})
            access_token = spotify.get("accessToken", "")

        try:
            response = spotify_api_request(
                SPOTIFY_CURRENT_TRACK_URL,
                access_token,
            )
        except HTTPError as error:
            if error.code == HTTPStatus.UNAUTHORIZED:
                self.send_json({"error": "unauthorized"})
                return
            if error.code == HTTPStatus.NO_CONTENT:
                self.send_json({"playing": False})
                return
            self.send_error(HTTPStatus.BAD_GATEWAY, "Spotify request failed")
            return
        except URLError:
            self.send_error(HTTPStatus.BAD_GATEWAY, "Spotify unavailable")
            return

        if response.status == HTTPStatus.NO_CONTENT:
            self.send_json({"playing": False})
            return

        payload = json.loads(response.read().decode("utf-8") or "{}")
        item = payload.get("item") or {}
        if not payload.get("is_playing") or not item:
            self.send_json({"playing": False})
            return

        artists = ", ".join(
            artist.get("name", "")
            for artist in item.get("artists", [])
            if artist.get("name")
        )
        self.send_json(
            {
                "playing": True,
                "title": item.get("name", ""),
                "artist": artists,
                "album": item.get("album", {}).get("name", ""),
            }
        )

    def send_html(self, file_path: Path) -> None:
        self.send_file(file_path, "text/html; charset=utf-8")

    def send_html_text(self, text: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = (
            "<!doctype html><html><body>"
            + text
            + "</body></html>"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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


class SpotifyAuthError(Exception):
    pass


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(payload: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_public_config() -> dict:
    config = deepcopy(load_config())
    spotify = config.get("spotify")
    if isinstance(spotify, dict):
        has_secret = bool(spotify.get("clientSecret"))
        authorized = bool(spotify.get("refreshToken"))
        spotify["clientSecret"] = ""
        spotify["accessToken"] = ""
        spotify["refreshToken"] = ""
        spotify["tokenExpiresAt"] = 0
        spotify["hasClientSecret"] = has_secret
        spotify["authorized"] = authorized
    return config


def merge_dashboard_payload(current: dict, incoming: dict) -> dict:
    merged = incoming
    spotify = merged.get("spotify")
    current_spotify = current.get("spotify", {})

    if isinstance(spotify, dict):
        spotify.pop("authorized", None)
        spotify.pop("hasClientSecret", None)
        if not spotify.get("clientSecret"):
            spotify["clientSecret"] = current_spotify.get("clientSecret", "")
        spotify["accessToken"] = current_spotify.get("accessToken", "")
        spotify["refreshToken"] = current_spotify.get("refreshToken", "")
        spotify["tokenExpiresAt"] = current_spotify.get("tokenExpiresAt", 0)

    return merged


def spotify_basic_auth(client_id: str, client_secret: str) -> str:
    token = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def spotify_token_request(client_id: str, client_secret: str, params: dict) -> dict:
    body = urlencode(params).encode("utf-8")
    request = Request(
        SPOTIFY_TOKEN_URL,
        data=body,
        headers={
            "Authorization": spotify_basic_auth(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError) as error:
        raise SpotifyAuthError("spotify authorization failed. you can close this tab.") from error


def apply_spotify_token_payload(spotify: dict, payload: dict) -> None:
    expires_in = int(payload.get("expires_in", 0) or 0)
    spotify["accessToken"] = payload.get("access_token", spotify.get("accessToken", ""))
    spotify["refreshToken"] = payload.get("refresh_token", spotify.get("refreshToken", ""))
    spotify["tokenExpiresAt"] = int(time.time() * 1000) + (expires_in * 1000)


def refresh_spotify_access_token(config: dict) -> None:
    spotify = config.get("spotify", {})
    client_id = spotify.get("clientId", "")
    client_secret = spotify.get("clientSecret", "")
    refresh_token = spotify.get("refreshToken", "")

    if not client_id or not client_secret or not refresh_token:
        raise SpotifyAuthError("spotify tokens are missing")

    payload = spotify_token_request(
        client_id,
        client_secret,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    apply_spotify_token_payload(spotify, payload)
    save_config(config)


def spotify_api_request(url: str, access_token: str):
    request = Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    return urlopen(request, timeout=15)


def ensure_layout() -> None:
    os.chdir(BASE)
    GIF_DIR.mkdir(parents=True, exist_ok=True)


def print_banner() -> None:
    print("── stream overlay server ─────────────────────────────")
    print(f"  dashboard            →  http://localhost:{PORT}/dashboard")
    print(f"  ticker               →  http://localhost:{PORT}/ticker")
    print(f"  gif background       →  http://localhost:{PORT}/gifbg")
    print(f"  spotify now playing  →  http://localhost:{PORT}/spotify")
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
