# Stream Overlay

Local OBS overlay suite with one Python server and two browser-source overlays:

- `ticker` at `http://localhost:8080/ticker`
- `gifbg` at `http://localhost:8080/gifbg`

Configuration is managed from the dashboard at `http://localhost:8080/dashboard`.

## Requirements

- Python 3
- OBS Studio

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

Recommended setup from the spec:

- Ticker: full stream width, about `30px` high, placed at the bottom
- GIF background: full canvas size, placed at the bottom of the source stack

## Dashboard

Open `http://localhost:8080/dashboard` in a normal browser.

From there you can:

- edit ticker speed, font size, separator, and items
- bulk import ticker items with optional `TAG:` prefix
- reorder, tag, and delete ticker items
- set GIF min/max duration
- adjust transition weights
- save each panel independently

After saving, refresh the affected OBS browser source manually.

## GIF Folder

Drop `.gif` files into:

```text
components/gifbg/gifs/
```

That folder is created automatically on startup if it does not exist.

## Project Files

- [`serve.py`](serve.py): stdlib HTTP server and routing
- [`config.json`](config.json): shared overlay config
- [`dashboard.html`](dashboard.html): config UI
- [`spec.md`](spec.md): detailed build spec
