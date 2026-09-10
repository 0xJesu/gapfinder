"""
ScrapeGraphAI hybrid layer for GapFinder.

- Uses the managed Cloud API v2 ONLY when SGAI_API_KEY is set (server-side only,
  never expose the key to the browser).
- Free pipeline (regex/DuckDuckGo) stays the default; AI fires on hot leads.
- Any 401/402/429/network failure -> caller falls back to the free pipeline.

Docs: https://docs.scrapegraphai.com/api-reference/introduction
Pricing: free tier = 500 one-time credits. extract=5cr, search=2cr/result.
"""
import os

import requests

BASE = "https://v2-api.scrapegraphai.com"
TIMEOUT = 45

LEAD_SCHEMA = {
    "type": "object",
    "properties": {
        "emails": {"type": "array", "items": {"type": "string"}},
        "phones": {"type": "array", "items": {"type": "string"}},
        "owner_name": {"type": "string"},
        "services": {"type": "array", "items": {"type": "string"}},
        "instagram": {"type": "string"},
        "facebook": {"type": "string"},
        "whatsapp": {"type": "boolean"},
        "has_booking": {"type": "boolean"},
        "has_pricing": {"type": "boolean"},
        "summary": {"type": "string"},
    },
}

LEAD_PROMPT = (
    "Extract contact and business audit signals from this local business website. "
    "Find every email address and phone number (including contact/about pages content). "
    "Detect: owner/manager name, list of services, Instagram/Facebook URLs, "
    "whether online booking exists, whether prices are listed, whether WhatsApp "
    "contact exists. Return empty arrays/strings (not null) when unknown."
)


class SGAIError(Exception):
    """Base error; caller should fall back to the free pipeline."""


class SGAIDisabled(SGAIError):
    """No API key configured."""


class SGAICredits(SGAIError):
    """Out of credits / rate-limited (402/429) — use free fallback."""


def _key():
    return (os.environ.get("SGAI_API_KEY") or "").strip()


def enabled():
    return bool(_key())


def _post(path, payload):
    key = _key()
    if not key:
        raise SGAIDisabled("SGAI_API_KEY not set")
    try:
        r = requests.post(
            BASE + path,
            json=payload,
            headers={"SGAI-APIKEY": key, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
    except Exception as ex:
        raise SGAIError(f"network: {ex}")
    if r.status_code in (402, 429):
        raise SGAICredits(f"credits/rate limit ({r.status_code})")
    if r.status_code in (401, 403):
        raise SGAIError(f"auth failed ({r.status_code})")
    try:
        body = r.json()
    except Exception:
        raise SGAIError(f"bad response ({r.status_code})")
    if r.status_code != 200 or body.get("status") != "success":
        raise SGAIError(body.get("error") or f"api {r.status_code}")
    return body.get("data") or {}


def credits():
    """Remaining balance; returns {} when disabled/unreachable (never raises)."""
    if not enabled():
        return {"enabled": False}
    try:
        r = requests.get(
            BASE + "/api/credits",
            headers={"SGAI-APIKEY": _key()},
            timeout=15,
        )
        if r.status_code == 200:
            d = r.json().get("data", {})
            d["enabled"] = True
            return d
    except Exception:
        pass
    return {"enabled": True, "unknown": True}


def search_website(name, area, country="in"):
    """Official-site discovery. ~6 credits (3 results x 2). Returns url or ''."""
    data = _post("/api/search", {
        "query": f"{name} {area} official website",
        "numResults": 3,
        "locationGeoCode": country,
    })
    for res in data.get("results", []) or []:
        url = (res.get("url") or "").strip()
        if not url:
            continue
        low = url.lower()
        if any(b in low for b in ("facebook.com", "instagram.com", "justdial",
                                  "yelp.", "tripadvisor", "zomato", "youtube.com")):
            continue
        return url[:160]
    return ""


def extract_lead(url):
    """Structured lead profile. 5 credits. Returns dict (possibly sparse)."""
    data = _post("/api/extract", {
        "url": url,
        "prompt": LEAD_PROMPT,
        "schema": LEAD_SCHEMA,
        "fetchConfig": {"mode": "auto"},
    })
    profile = data.get("json_data") or data.get("json") or {}
    if not isinstance(profile, dict):
        return {}
    # normalize: no nulls
    for k in ("emails", "phones", "services"):
        if not isinstance(profile.get(k), list):
            profile[k] = []
    for k in ("owner_name", "instagram", "facebook", "summary"):
        if profile.get(k) is None:
            profile[k] = ""
    for k in ("whatsapp", "has_booking", "has_pricing"):
        profile[k] = bool(profile.get(k))
    return profile
