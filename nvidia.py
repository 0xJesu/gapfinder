"""
NVIDIA NIM layer for GapFinder (optional, keyed).

Unlike ScrapeGraphAI Extract (which fetches the URL itself), NVIDIA NIM is
pure LLM inference: WE fetch the page, strip it to text, and ask the model
for strict JSON. Endpoint is OpenAI-compatible:
    POST https://integrate.api.nvidia.com/v1/chat/completions

Key lives ONLY in the NVIDIA_API_KEY env var (server-side, never in browser
code, never committed). Default model is configurable via NVIDIA_MODEL.

Docs: https://build.nvidia.com  (key dashboard + model catalog)
"""
import json
import os
import re

import requests

BASE = "https://integrate.api.nvidia.com/v1"
TIMEOUT = 60
MAX_CHARS = 12000  # page text budget per call

DEFAULT_MODEL = "openai/gpt-oss-20b"  # verified 200 on typical build.nvidia keys

SYSTEM = (
    "You extract structured business data from website text. "
    "Reply with JSON ONLY, no markdown fences, matching exactly these keys: "
    '{"emails": [], "phones": [], "owner_name": "", "services": [], '
    '"instagram": "", "facebook": "", "whatsapp": false, '
    '"has_booking": false, "has_pricing": false, "summary": ""}. '
    "Use empty arrays/strings/false (never null) when unknown."
)

UA = {"User-Agent": "GapFinder/1.0 (local lead research)"}


class NVError(Exception):
    """Caller should fall back (free pipeline or other engine)."""


class NVDisabled(NVError):
    pass


def _key():
    return (os.environ.get("NVIDIA_API_KEY") or "").strip()


def _model():
    return (os.environ.get("NVIDIA_MODEL") or DEFAULT_MODEL).strip()


def enabled():
    return bool(_key())


def _page_text(url):
    """Fetch + strip to readable text. Raises NVError on failure."""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        r = requests.get(url, headers=UA, timeout=12)
        if r.status_code >= 400:
            raise NVError(f"fetch {r.status_code}")
        html = r.text or ""
    except NVError:
        raise
    except Exception as ex:
        raise NVError(f"fetch failed: {ex}")
    # strip scripts/styles/tags without bs4 dependency
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    # de-obfuscate common email tricks before the model sees them
    text = re.sub(r"\s*\[at\]\s*", "@", text)
    text = re.sub(r"\s*\[dot\]\s*", ".", text)
    if len(text) < 50:
        raise NVError("page nearly empty (JS-rendered or blocked)")
    return text[:MAX_CHARS]


def _chat(page_text, url):
    return _complete(SYSTEM,
                     f"Website URL: {url}\n\nPAGE TEXT:\n{page_text}", 2048)


SUMMARY_SYSTEM = (
    "You write short business summaries for a sales researcher. "
    "Reply with JSON ONLY, no markdown fences: "
    '{"summary": "2-3 sentence plain-English description of what the business is and does", '
    '"bullets": ["up to 5 short facts: services, contact, online presence"]}. '
    "If facts are inferred rather than stated on the site, start summary with 'Likely '."
)


def summarize(context):
    """One-shot prose summary from already-gathered facts. Returns dict."""
    raw = _complete(SUMMARY_SYSTEM, context[:6000], 1024)
    if not isinstance(raw, dict):
        raise NVError("model JSON was not an object")
    return {"summary": str(raw.get("summary") or "")[:800],
            "bullets": [str(b)[:160] for b in (raw.get("bullets") or [])
                        if b][:6]}


def _complete(system, user_text, max_tokens):
    key = _key()
    if not key:
        raise NVDisabled("NVIDIA_API_KEY not set")
    base_payload = {
        "model": _model(),
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    }

    def _call(with_json_mode):
        payload = dict(base_payload)
        if with_json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            return requests.post(
                BASE + "/chat/completions",
                headers={"Authorization": "Bearer " + key,
                         "Content-Type": "application/json"},
                json=payload, timeout=TIMEOUT,
            )
        except Exception as ex:
            raise NVError(f"network: {ex}")

    r = _call(True)
    if r.status_code == 400:  # model lacks JSON mode → plain prompt retry
        r = _call(False)
    if r.status_code in (401, 403):
        raise NVError(f"auth failed ({r.status_code}) — check key")
    if r.status_code == 429:
        raise NVError("rate limited (429)")
    if r.status_code == 404:
        raise NVError(f"model not enabled for this key ({r.text[:120]}) — "
                      "try NVIDIA_MODEL=openai/gpt-oss-20b or moonshotai/kimi-k3")
    if r.status_code != 200:
        raise NVError(f"api {r.status_code}: {r.text[:150]}")
    try:
        msg = r.json()["choices"][0]["message"]
        content = msg.get("content") or ""
    except Exception:
        raise NVError("unexpected response shape")
    if not content.strip():
        raise NVError("model returned no text (reasoning-only model?) — "
                      "set NVIDIA_MODEL=openai/gpt-oss-20b")
    # tolerate fences just in case
    content = re.sub(r"^```(?:json)?|```$", "", content.strip())
    try:
        profile = json.loads(content)
    except Exception:
        raise NVError("model did not return JSON")
    if not isinstance(profile, dict):
        raise NVError("model JSON was not an object")
    return profile


def extract_lead(url):
    """Structured lead profile dict (same shape as sgai.extract_lead)."""
    text = _page_text(url)
    profile = _chat(text, url)
    for k in ("emails", "phones", "services"):
        if not isinstance(profile.get(k), list):
            profile[k] = []
    for k in ("owner_name", "instagram", "facebook", "summary"):
        if profile.get(k) is None:
            profile[k] = ""
    for k in ("whatsapp", "has_booking", "has_pricing"):
        profile[k] = bool(profile.get(k))
    return profile
