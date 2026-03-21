# Stream Overlay — Agent Build Spec

## Overview

A local stream overlay suite for OBS. One Python server handles all routing. Each overlay
component lives at its own URL and is added in OBS as a separate browser source, which allows
independent positioning, sizing, and z-ordering per source.

A single dashboard at `/dashboard` controls all components. Config is stored in one
`config.json` with a keyed section per component.

Adding a new component requires: creating `components/<name>/index.html`, adding a config
section to `config.json`, registering one route in `serve.py`, and adding a dashboard panel
in `dashboard.html`. Nothing else changes.

---

## Project Structure

```
stream-overlay/
  serve.py                   ← single HTTP server for everything
  config.json                ← one config section per component
  dashboard.html             ← unified dashboard, one panel per component
  components/
    ticker/
      index.html             ← served at /ticker
    gifbg/
      index.html             ← served at /gifbg
      gifs/                  ← user drops .gif files here
```

---

## Component 1 — `serve.py`

Python 3 stdlib only. No third-party dependencies.

### Routes

| Method | Path | Behavior |
|---|---|---|
| GET | `/dashboard` | serve `dashboard.html` |
| GET | `/config` | return full `config.json` as JSON |
| POST | `/config` | write request body to `config.json` |
| GET | `/ticker` | serve `components/ticker/index.html` |
| GET | `/gifbg` | serve `components/gifbg/index.html` |
| GET | `/gifbg/gifs/` | directory listing of `components/gifbg/gifs/` |
| GET | `/gifbg/gifs/<file>` | serve individual gif file |

**Adding a new component** requires only adding its route block here. No other files change.

### Implementation Notes
- `os.chdir` to the script's own directory on startup
- Create `components/gifbg/gifs/` on startup if it doesn't exist
- Directory listing for `/gifbg/gifs/` must emit `<a href="/gifbg/gifs/filename.gif">` hrefs
  so the overlay can parse them via regex
- Suppress 200/304 log noise, only log errors
- `Access-Control-Allow-Origin: *` on all responses
- Handle OPTIONS for CORS preflight
- Port: `8080`
- Startup output:
  ```
  ── stream overlay server ─────────────────────────────
    dashboard       →  http://localhost:8080/dashboard
    ticker          →  http://localhost:8080/ticker
    gif background  →  http://localhost:8080/gifbg
  ──────────────────────────────────────────────────────
    ctrl+c to stop
  ```

---

## Component 2 — `config.json`

One top-level key per component. The dashboard reads the full file and renders one panel per
key. Overlays read only their own section.

### Schema

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
  }
}
```

### Field Reference

`ticker.speed` — CSS animation duration in seconds. Lower = faster scroll.
`ticker.fontSize` — px, applied to all ticker spans.
`ticker.separator` — character rendered between items.
`ticker.items[].cls` — `""` for default dim style, `"tag"` for bright white bold.

`gifbg.minDuration` / `gifbg.maxDuration` — ms range for random display time per gif.
`gifbg.transitions` — map of transition name to pool slot count. `0` disables that transition.

### Extending
Adding a new component means adding a new top-level key with whatever shape that component
needs. The dashboard must be updated to render a panel for the new key (see Component 5).

---

## Component 3 — `components/ticker/index.html`

### OBS Setup
- URL: `http://localhost:8080/ticker`
- Width: stream width (e.g. 1920), Height: ~30px
- Position at bottom of canvas
- Background transparent — body must have `background: transparent`

### Behavior
On load: `GET /config`, read `config.ticker`. Apply `speed`, `fontSize`, `separator`, `items`.

Render a horizontally scrolling bar:
- `div.ticker-wrap` containing `div.ticker-track`
- Track HTML duplicated twice for seamless CSS loop
- Animation: `translateX(0)` → `translateX(-50%)` over `{speed}s` linear infinite
- Hover pauses animation

### Style
- Wrap background: `rgba(0,0,0,0.72)`, top border: `1px solid rgba(255,255,255,0.08)`
- Left/right fade via `::before` / `::after` gradient pseudo-elements
- Font: `Share Tech Mono` (Google Fonts), size from config, `letter-spacing: 0.04em`
- Default item color: `rgba(210,210,210,0.85)`
- Tag item: `rgba(255,255,255,0.95)`, bold
- Separator: `rgba(255,255,255,0.2)`

Ticker rendering separates regular items from `cls: "tag"` items, then inserts one tag after
every 2 regular items. Tag order is preserved and wraps if there are more fact slots than tags.

---

## Component 4 — `components/gifbg/index.html`

### OBS Setup
- URL: `http://localhost:8080/gifbg`
- Width/height: full stream resolution
- Place at bottom of source stack (behind everything)

### Behavior
On load:
1. `GET /config`, read `config.gifbg`
2. Build weighted transition pool from `transitions` map
3. `GET /gifbg/gifs/`, parse `href` links for `.gif` files
4. If no gifs: show error text and stop
5. Begin playback loop: pick random gif (no immediate repeat), pick random transition,
   fire transition with callback that sets `img.src`, wait `randBetween(min, max)` ms, repeat

### Style
- `body`: `background: #000`, `overflow: hidden`, `100vw × 100vh`
- `#gif`: `position: fixed`, `inset: 0`, `100% × 100%`, `object-fit: cover`
- `image-rendering: pixelated` + `image-rendering: crisp-edges` — mandatory, never soften
- No color grading, blend modes, or CSS filters

### Z-index Stack
| Element | z-index | Role |
|---|---|---|
| `#gif` | 0 | current gif |
| `#fx` canvas | 5 | transition drawing |
| `#flash` div | 10 | white flash overlay |

### Transitions
Each has signature `fn(callback)`. Callback is called mid-transition when screen is most
obscured. Pool is built by pushing each function N times where N = its weight value.
Fallback to `[nothing]` if pool is empty.

`nothing(cb)` — call cb immediately.

`hardFlash(cb)` — flash `#flash` to opacity 1 instantly, call cb, then on double rAF fade
back to 0 over 0.25s ease-out.

`doubleFlash(cb)` — `hardFlash` with empty cb, then 130ms later `hardFlash` with real cb.

`venetianBlinds(cb)` — canvas, 10 horizontal slices wipe left-to-right, 400ms, cb at t=0.5.

`pixelDissolve(cb)` — canvas, 24×14 grid, Fisher-Yates shuffle, fill cells in order, 500ms,
cb at t=0.5.

`starWipe(cb)` — canvas, black fill then `destination-out` growing 5-point star from center,
quadratic ease-in-out radius, inner = outer × 0.45, 600ms, cb at t=0.4.

`blockFlip(cb)` — CSS 3D, `perspective(600px) rotateY(90deg)` ease-in 350ms, swap at 350ms,
`rotateY(0deg)` ease-out 350ms, clean up styles.

`zoomPunch(cb)` — CSS `scale(1.15)` ease-in 200ms, swap at 200ms, `scale(1)` ease-out 300ms,
clean up styles.

---

## Component 5 — `dashboard.html`

### Purpose
Single-page config UI at `http://localhost:8080/dashboard`. Opened in a browser, not OBS.
Reads `GET /config` on load, renders one panel per top-level config key, POSTs back on save.

### Aesthetic
Dark terminal. Non-negotiable:
- Background `#0a0a0a`, panels `#111111`, borders `#2a2a2a`
- Phosphor green `#39ff6e` — primary actions, tag highlights, save buttons
- Amber `#ffb300` — panel headings, range sliders
- Red `#ff4444` — destructive actions
- Fonts: `VT323` (Google Fonts) for all headings, `Share Tech Mono` for body and controls
- Fixed `repeating-linear-gradient` scanline pseudo-element over the whole page
- Header title `// OVERLAY DASHBOARD` with green `text-shadow` glow
- Pulsing green dot in status bar via CSS keyframe animation

### Layout
- Fixed header: title + subtitle (`stream config`)
- Status bar: pulsing dot, gif count, ticker item count (populated from config on load)
- Below: horizontal scrollable row of panels, one per component, full remaining viewport height
- Each panel: header (amber title + route hint), scrollable body, fixed save bar at bottom

This horizontal layout means new components are added as new panels to the right — no layout
restructuring needed.

### Panel — Ticker

**Display controls:**
- Number input `speed` (30–600, step 10) — label: "scroll speed (s)" with hint "lower = faster"
- Number input `fontSize` (8–32, step 1) — label: "font size (px)"
- Text input `separator` (maxlength 4, narrow) — label: "separator"

**Items controls:**
- "bulk import" button → opens import modal
- "clear all" button → confirm dialog, clears items array
- Drag-and-drop sortable list of current items:
  - Each row: drag handle `⠿`, item text (truncated, green if tag), tag toggle button, delete `×`
  - HTML5 drag API, visual border highlight on drag-over
- Add-item row: text input (Enter submits), tag toggle button, `+ add` button

**Save bar:** status message + "save ticker →" button

### Panel — Gif Background

**Timing controls:**
- Number input `minDuration` (1000–60000, step 500) — label: "min duration (ms)"
- Number input `maxDuration` (1000–60000, step 500) — label: "max duration (ms)"
- Validate min < max on save

**Transition weights:**
- Hint: "slots in pool. 0 = disabled."
- One row per transition: label, range slider 0–8 (amber accent), numeric readout
- Transitions and display labels:
  - `nothing` → "hard cut"
  - `hardFlash` → "flash"
  - `doubleFlash` → "double flash"
  - `venetianBlinds` → "venetian blinds"
  - `pixelDissolve` → "pixel dissolve"
  - `starWipe` → "star wipe ⭐"
  - `blockFlip` → "3d block flip"
  - `zoomPunch` → "zoom punch"

**Save bar:** status message + "save gif bg →" button

### Bulk Import Modal (Ticker only)

Centered overlay, closes on backdrop click or cancel.

- Textarea: one item per line
- Lines starting with `TAG:` (case-insensitive) → imported as `cls: "tag"`, prefix stripped
- Blank lines ignored
- Items appended to existing list (never replaces)
- On import: close modal, re-render list, show count message e.g. "imported 12 items"

### Save Behavior
- Each panel saves independently
- On save: read panel inputs → mutate in-memory config object → `POST /config` with full JSON
- Success: show "saved. refresh OBS sources to apply." (auto-clear 4s)
- Error: show error text (auto-clear 4s)
- No live reload. User manually refreshes OBS browser source after saving.

---

## Adding a New Component — Checklist

1. Create `components/<name>/index.html`
   - `GET /config` on load, read `config.<name>`
   - Implement the overlay behavior

2. Add a config section to `config.json`:
   ```json
   "<name>": { ...default values... }
   ```

3. Add a route to `serve.py`:
   ```python
   elif p == "/<name>":
       self.send_html(BASE / "components" / "<name>" / "index.html")
   ```
   If the component needs static assets (e.g. a subfolder), add those sub-routes too.

4. Add a panel to `dashboard.html`:
   - One new panel `div` in the horizontal panel row
   - Reads from `config.<name>` on init
   - Writes back to `config.<name>` on save (full config is always POSTed)
   - Add a line to the status bar if relevant

5. Print the new route in `serve.py` startup output.

---

## Constraints

- All HTML files are single self-contained files — no bundlers, no external JS/CSS files
- Vanilla JS and CSS only
- Google Fonts imports acceptable (internet available)
- Python server uses stdlib only — no Flask, no pip installs
- `image-rendering: pixelated` on gif overlay is non-negotiable
- No color grading or CSS filters on the gif background
