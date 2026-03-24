# Stream Overlay Suite

Local OBS overlay suite with one Python server and three browser-source components:

- `ticker` at `http://localhost:8080/ticker`
- `gifbg` at `http://localhost:8080/gifbg`
- `spotify` at `http://localhost:8080/spotify`

All configuration is managed from the dashboard at `http://localhost:8080/dashboard`.

## Requirements

- Python 3
- OBS Studio
- A Spotify developer app if you want to use the Spotify component

No third-party Python packages are required.

## Run

```bash
python3 serve.py
```

The server listens on `http://localhost:8080`.

## OBS Setup

Add these as separate Browser Sources in OBS:

- Ticker: `http://localhost:8080/ticker`
- GIF background: `http://localhost:8080/gifbg`
- Spotify now playing: `http://localhost:8080/spotify`

Typical placement:

- Ticker: full stream width, short strip at the bottom
- GIF background: full canvas size, bottom of the source stack
- Spotify: wherever you want the now-playing text to appear

## Dashboard

Open `http://localhost:8080/dashboard` in a normal browser.

Current dashboard capabilities:

- Ticker: speed, font size, separator, edit-all modal, drag reorder, tag toggles
- GIF background: timing controls and transition weights
- Spotify: client ID, masked client secret entry, poll interval, auth status, authorize flow

Each panel saves independently. After saving, refresh the affected OBS browser source manually.

## Spotify Setup

Spotify credentials and token exchange are handled server-side.

1. Create a Spotify app at [developer.spotify.com](https://developer.spotify.com)
2. Set the redirect URI to `http://localhost:8080/spotify/callback`
3. Open the dashboard and enter the Spotify client ID and client secret
4. Save the Spotify panel
5. Click `authorize with spotify →`
6. Approve the OAuth request
7. After the callback succeeds, the Spotify overlay will poll the local proxy endpoint automatically

Required scope: `user-read-currently-playing`

## GIF Folder

Drop `.gif` files into:

```text
components/gifbg/gifs/
```

That folder is created automatically on startup if it does not exist.

## Project Files

- [`serve.py`](serve.py): stdlib HTTP server, config handling, Spotify OAuth/proxy routes
- [`config.json`](config.json): shared component config
- [`dashboard.html`](dashboard.html): unified config UI
- [`spec.md`](spec.md): current implementation spec for the suite
