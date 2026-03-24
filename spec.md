# Stream Overlay — Current Suite Spec

## Overview

One local Python server hosts the dashboard, serves all overlay pages, stores the shared
`config.json`, and handles Spotify OAuth/token refresh server-side.

Current components:

- `ticker` at `/ticker`
- `gifbg` at `/gifbg`
- `spotify` at `/spotify`

The dashboard lives at `/dashboard`.

---

## Project Structure

```text
stream-overlay/
  serve.py
  config.json
  dashboard.html
  components/
    ticker/
      index.html
    gifbg/
      index.html
      gifs/
    spotify/
      index.html
```

---

## Server

`serve.py` uses Python stdlib only.

### Core routes

| Method | Path | Behavior |
|---|---|---|
| GET | `/dashboard` | serve `dashboard.html` |
| GET | `/config` | return public config JSON |
| POST | `/config` | save dashboard config changes |
| GET | `/ticker` | serve ticker overlay |
| GET | `/gifbg` | serve GIF background overlay |
| GET | `/gifbg/gifs/` | return GIF directory listing |
| GET | `/gifbg/gifs/<file>` | serve a GIF file |
| GET | `/spotify` | serve Spotify overlay |
| GET | `/spotify/callback` | handle Spotify OAuth callback |
| GET | `/spotify/now-playing` | proxy current Spotify playback state |

### Config handling

- `GET /config` redacts Spotify secrets and tokens before sending config to the browser
- `POST /config` preserves server-managed Spotify token fields
- `Access-Control-Allow-Origin: *` is sent on all responses
- `OPTIONS` is handled for CORS preflight
- `components/gifbg/gifs/` is created on startup if missing
- Normal 200/204/304 request noise is suppressed in the log output

### Spotify server behavior

- Spotify token exchange and refresh use `urllib.request`
- Redirect URI is `http://localhost:8080/spotify/callback`
- Access tokens are refreshed when less than 60 seconds remain
- `/spotify/now-playing` returns one of:
  - `{ "playing": false }`
  - `{ "playing": true, "title": "...", "artist": "...", "album": "..." }`
  - `{ "error": "unauthorized" }`

---

## Config Shape

```json
{
  "ticker": {
    "speed": 180,
    "fontSize": 12,
    "separator": "·",
    "items": [
      { "text": "string", "cls": "" },
      { "text": "string", "cls": "tag" }
    ]
  },
  "gifbg": {
    "minDuration": 5000,
    "maxDuration": 15000,
    "transitions": {
      "nothing": 4,
      "hardFlash": 2,
      "doubleFlash": 1,
      "venetianBlinds": 1,
      "pixelDissolve": 1,
      "starWipe": 1,
      "blockFlip": 1,
      "zoomPunch": 1
    }
  },
  "spotify": {
    "clientId": "",
    "clientSecret": "",
    "accessToken": "",
    "refreshToken": "",
    "tokenExpiresAt": 0,
    "pollInterval": 10000
  }
}
```

`spotify.clientSecret`, `spotify.accessToken`, `spotify.refreshToken`, and
`spotify.tokenExpiresAt` are stored in `config.json` but are not exposed back to the browser
in plaintext through `GET /config`.

---

## Ticker Component

### Behavior

- Reads `config.ticker` from `/config`
- Builds a horizontally scrolling track duplicated twice for a seamless loop
- Applies `speed`, `fontSize`, `separator`, and `items` from config
- Pauses animation on hover

### Item logic

- Regular items are `cls: ""`
- Highlighted/social items are `cls: "tag"`
- Rendering separates regular items and tag items, then inserts one tag after every 2 regular
  items
- Tag order is preserved and wraps if there are more fact slots than tags

### Styling

- Transparent body
- Dark ticker strip with left/right fade edges
- `Share Tech Mono`
- Dim regular items, bright bold tag items

---

## GIF Background Component

### Behavior

- Reads `config.gifbg` from `/config`
- Reads available `.gif` files from `/gifbg/gifs/`
- If no GIFs exist, shows an error message and stops
- Chooses a random GIF without immediate repeat
- Chooses transitions from a weighted pool built from the config

### Constraints

- Full-screen background overlay
- `image-rendering: pixelated` and `crisp-edges` stay enabled
- No CSS filters or color grading

---

## Spotify Component

### Overlay behavior

- Reads `config.spotify.pollInterval` from `/config`
- Polls `/spotify/now-playing`
- Starts hidden
- Shows title, artist, and album only when a track is playing
- Stops polling and shows `spotify: not authorized` on auth failure
- Avoids DOM updates when title and artist have not changed

### Markup

The overlay keeps logic and text nodes only:

- `#sp-title`
- `#sp-artist`
- `#sp-album`

No design system or layout styling is baked into the Spotify overlay.

---

## Dashboard

### Layout

- Dark terminal-style single-page UI at `/dashboard`
- Horizontal panel row with one panel per component
- Independent save bar per panel

### Ticker panel

- Speed, font size, separator
- Item list with drag reorder, tag toggle, delete
- `edit all` modal using one line per item
- `TAG:` prefix marks tag items

### GIF background panel

- Min/max duration inputs
- Transition weight sliders

### Spotify panel

- Client ID input
- Client secret password field
- Poll interval input (`3000` to `30000`, step `1000`)
- `authorize with spotify →` button
- Auth status indicator
- Save flow that updates credentials/poll interval without overwriting tokens

---

## Adding a Component

1. Create `components/<name>/index.html`
2. Add defaults in `config.json`
3. Add route handling in `serve.py`
4. Add a dashboard panel in `dashboard.html`
5. Update the startup banner

Keep any secrets or third-party credentials server-side when the component needs external APIs.
