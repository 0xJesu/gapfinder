# ◈ GapFinder — Local Business Lead Engine

Find local businesses that desperately need a website. Live OpenStreetMap data →
website guessing → email crawling → free MX verification → hot-lead scoring.
**$0 in paid APIs.** Runs on your machine, mobile-friendly, with an animated
liquid-glass hero on top.

![Hero](assets/hero.png)
![App on mobile](assets/app-mobile.png)

> Built for agencies & freelancers who sell websites, SEO, and online-presence
> services to local SMBs (salons, clinics, gyms, restaurants, hotels…).

---

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Install](#install)
- [Host locally](#host-locally)
- [Test on your phone](#test-on-your-phone)
- [Configuration](#configuration)
- [AI Enrich (optional)](#ai-enrich-optional)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Scope](#scope)
- [Costs](#costs)
- [Legal & responsible use](#legal--responsible-use)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

| Area | What you get |
|---|---|
| 🛰️ **Discovery** | Search any locality + niche → live businesses from OpenStreetMap Overpass API (3 mirrors with automatic fallback) |
| 🔍 **Enrich** | Auto-guesses missing websites (DuckDuckGo), crawls contact pages (de-obfuscates `[at]`/`[dot]`), classifies `no-website / dead-site / thin-site / has-website` |
| ✉️ **Verify free** | Syntax + DNS MX/A checks via `dnspython`, role-address fallback (`info@`, `contact@`, `hello@`) |
| ✨ **AI Enrich** | Optional ScrapeGraphAI layer for hot leads: official-site search + structured profile (owner, services, booking, pricing, socials). Free pipeline stays the default |
| 📊 **Dashboard** | Cards ⇄ sortable table (score, niche, website, emails, source). Stacked-row layout on phones — no sideways scrolling |
| 📍 **Verify on Maps** | Every lead has a **Check Maps** button (Google Maps search for that exact business) to confirm it truly has no website |
| 📞 **Tap-to-call** | `tel:` call buttons wherever a phone exists — opens the dialer directly on mobile |
| ⬇️ **CSV export** | One-click export (name, category, address, phone, website, emails, MX, score, engine, reasons) |
| 📱 **Mobile-first** | 44–48px touch targets, bottom action bar, safe-area support, no iOS input zoom, liquid-glass UI |

![Dashboard on mobile](assets/dashboard-mobile.png)

---

## How it works

```
Area + niche
   │  Nominatim (geocode → bbox)
   ▼
Overpass API ──► leads (name, category, address, phone, website?)
   │  DuckDuckGo guess (if no site) → crawl /contact /about → regex emails
   ▼
DNS MX verify ──► 0–100 score + reasons ──► cards / dashboard / CSV
   │  optional: ✨ AI Enrich on hot leads (ScrapeGraphAI cloud)
```

Scoring: no website **+35**, dead site **+25**, thin site **+15**, no phone/email
**+10** each. Higher = hotter agency lead.

---

## Install

**Requirements:** Python 3.10+ · `pip` · internet access. No Docker, no API keys.

Windows (PowerShell):

```powershell
git clone https://github.com/0xjesu/gapfinder.git
cd gapfinder
pip install -r requirements.txt
python app.py
```

macOS / Linux:

```bash
git clone https://github.com/0xjesu/gapfinder.git
cd gapfinder
pip3 install -r requirements.txt
python3 app.py
```

Dependencies (`requirements.txt`): `flask`, `requests`, `beautifulsoup4`,
`dnspython`, `lxml` — all free, all open.

---

## Host locally

```powershell
python app.py
# → http://127.0.0.1:5000
```

That's it — Flask serves the UI + API on your machine. Your searches never
leave your computer except for calls to free public services (OSM, DuckDuckGo,
target websites, DNS).

| Env var | Default | Purpose |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind address (`0.0.0.0` = reachable on your LAN) |
| `PORT` | `5000` | Port |
| `SGAI_API_KEY` | *(unset)* | Enables ✨ AI Enrich (optional, see below) |

Examples:

```powershell
$env:PORT="8000"; python app.py          # custom port
$env:HOST="0.0.0.0"; python app.py       # LAN-visible (phone testing)
```

---

## Test on your phone

`localhost` never reaches a phone, so expose the laptop on your Wi-Fi:

1. Run with `$env:HOST="0.0.0.0"; python app.py`
2. Find your laptop IP (`ipconfig` → IPv4, e.g. `192.168.29.60`)
3. On your phone (same Wi-Fi): `http://192.168.29.60:5000`

If the page won't load, allow Python through Windows Firewall (admin PowerShell):

```powershell
New-NetFirewallRule -DisplayName "GapFinder" -Direction Inbound `
  -Program "C:\Users\<you>\AppData\Local\Programs\Python\Python313\python.exe" `
  -Action Allow -Profile Private
```

Call buttons open the phone dialer directly — that's where they shine.

---

## Configuration

Copy-paste tunables live in `app.py`:

- `OVERPASS_MIRRORS` — tried in order when one is busy
- Search bbox `d = 0.02` (~2 km each side; keeps Overpass fast)
- `score_lead()` weights (35/25/15/10, capped at 100)
- Demo data in `/api/demo` (offline-safe sample leads)

---

## AI Enrich (optional)

`sgai.py` adds a hybrid ScrapeGraphAI layer. Default stays 100% free; AI fires
only when you tap ✨ on a hot lead.

1. Get a free key at [scrapegraphai.com/dashboard](https://scrapegraphai.com/dashboard)
   (500 one-time credits ≈ ~45 hot leads: ~6 for site search + 5 for extraction)
2. Set it server-side (**never in browser code**) and restart:

```powershell
setx SGAI_API_KEY "sgai-..."
python app.py
```

The header pill shows `● AI on` when keyed. On 401/402/429 the endpoint
returns `engine: "free-fallback"` and the UI tells you — the tool never breaks.

---

## API reference

Base: `http://127.0.0.1:5000`

| Method & path | Purpose |
|---|---|
| `GET /` | UI (hero + tool) |
| `GET /api/health` | `{ok, dns, sgai:{enabled}, time}` |
| `GET /api/geocode?q=` | Place → bbox + lat/lon (Nominatim) |
| `POST /api/search` | `{area\|bbox, category, max}` → leads |
| `POST /api/enrich` | `{name, area, website, phone}` → emails, MX, score |
| `POST /api/ai-enrich` | Same, via ScrapeGraphAI (`engine: ai\|free-fallback\|disabled`) |
| `GET /api/demo` | 6 sample leads (works offline) |

---

## Project structure

```
gapfinder/
├── app.py              # Flask backend: OSM + crawl + MX + scoring + API
├── sgai.py             # Optional ScrapeGraphAI hybrid layer (needs key)
├── requirements.txt
├── templates/
│   └── index.html      # Liquid-glass hero + tool UI (single file, mobile-first)
├── hero/               # Standalone React + TS + Vite + Tailwind hero source
│   ├── src/App.tsx
│   ├── src/index.css   # .liquid-glass spec
│   └── package.json    # npm install; npm run dev
└── assets/             # README screenshots
```

Prefer the React hero standalone? `cd hero && npm install && npm run dev`.

---

## Scope

**In scope**

- Local-SMB lead discovery via free, keyless public data (OSM/Overpass/Nominatim)
- Website-gap detection, contact crawling, $0 email verification, lead scoring
- Agency workflow: dashboard → Maps-verify → call → CSV outreach
- Optional, clearly-marked AI upgrade path that degrades gracefully

**Out of scope / limitations**

- Not an Apollo/ZoomInfo/Clay replacement — no 200M-contact DB, no waterfall
  enrichment, no intent data. Those need paid APIs by nature.
- OSM coverage varies by region; tags (`phone`/`website`) are patchy outside
  well-mapped cities.
- Free MX checks can't resolve catch-all domains (20–40% of B2B inboxes) or
  Gmail/Yahoo decision-makers — treat `role@` guesses as leads, not guarantees.
- Enrichment is deliberately polite (timeouts, delays) — bulk runs take minutes.
- No auth/multi-user: it's a local single-user tool. Don't expose it to the
  public internet without adding authentication and rate-limiting.
- A previous Google-Maps-scraper integration was removed (needs Docker, legally
  grey, flaky) — the **Check Maps** verify links cover the verification need.

---

## Costs

| Mode | Cost |
|---|---|
| Default pipeline (OSM + crawl + MX) | **$0 forever**, no keys |
| ✨ AI Enrich | $0 on the 500-credit free tier, then from $20/mo (your key, your spend) |
| Hosting | $0 locally · ~$5/mo VPS if you outgrow localhost |

---

## Legal & responsible use

- OSM data is © OpenStreetMap contributors, ODbL (attribution shown in-app).
- Respect `robots.txt`, rate limits, and terms of target sites when crawling.
- Scraped phones/emails are personal data: follow GDPR / CCPA / CAN-SPAM
  (consent or documented legitimate interest, opt-outs, no spam).

---

## Roadmap

- [ ] Playwright-backed crawl for JS-heavy sites (optional, local)
- [ ] Lighthouse batch audit per lead (performance/SEO scores in dashboard)
- [ ] `Dockerfile` + rate-limiting for safe VPS deployment
- [ ] Saved searches + lead revisit/notes (SQLite)

---

## License

MIT — see [LICENSE](LICENSE).
