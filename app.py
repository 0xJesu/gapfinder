"""
Local Business Gap Finder — $0 paid APIs
Stack: Flask + Overpass (OSM) + Nominatim + DuckDuckGo + crawl + DNS/MX verify
Run locally: python app.py  ->  http://127.0.0.1:5000
"""
import re
import time
import socket
import random
from urllib.parse import urlparse, quote_plus

import requests
from flask import Flask, request, jsonify, render_template

try:
    import dns.resolver
    HAS_DNS = True
except Exception:
    HAS_DNS = False

try:
    import sgai
    HAS_SGAI = True
except Exception:
    HAS_SGAI = False

app = Flask(__name__)

UA = {"User-Agent": "LocalGapFinder/1.0 (vibe-coding demo; contact: demo@localhost)"}
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]

CHAIN_NAMES = {"mcdonald", "starbucks", "kfc", "dominos", "pizza hut", "subway",
               " reliance", "dmart", "decathlon", "zara", "h&m", "costa", "burger king"}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
OBFUSCATION_PATTERNS = [
    (re.compile(r"\s*\[at\]\s*", re.I), "@"),
    (re.compile(r"\s*\(at\)\s*", re.I), "@"),
    (re.compile(r"\s*\{at\}\s*", re.I), "@"),
    (re.compile(r"\s+at\s+", re.I), "@"),
    (re.compile(r"\s*\[dot\]\s*", re.I), "."),
    (re.compile(r"\s*\(dot\)\s*", re.I), "."),
    (re.compile(r"\s*\{dot\}\s*", re.I), "."),
    (re.compile(r"\s+dot\s+", re.I), "."),
]

# ---------- helpers ----------

def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

@app.after_request
def after(resp):
    return add_cors(resp)

def deobfuscate(text):
    for pat, rep in OBFUSCATION_PATTERNS:
        text = pat.sub(rep, text)
    return text

def clean_emails(raw_list):
    out, seen = [], set()
    bad_ext = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
    for e in raw_list:
        e = e.strip().lower().rstrip(".,;:")
        if e.endswith(bad_ext):
            continue
        if "example." in e or "sentry" in e or "wixpress" in e:
            continue
        if "@" not in e or len(e) > 80:
            continue
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out[:10]

def extract_domain(url):
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        host = urlparse(url).netloc.lower()
        host = host.replace("www.", "")
        host = host.split(":")[0].split("/")[0]
        return host
    except Exception:
        return ""

def check_mx(domain):
    """Free MX check. Returns (mx_valid: bool, detail: str)."""
    if not domain or "." not in domain:
        return False, "bad-domain"
    if not HAS_DNS:
        # socket fallback: can we resolve?
        try:
            socket.getaddrinfo(domain, 80)
            return True, "dns-resolves (dnspython missing)"
        except Exception:
            return False, "unresolvable"
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 6
        answers = resolver.resolve(domain, "MX")
        if answers:
            return True, f"{len(answers)} MX"
    except Exception as ex:
        # fallback A record
        try:
            resolver.resolve(domain, "A")
            return True, "no MX, has A"
        except Exception:
            return False, f"no-mx ({type(ex).__name__})"
    return False, "no-mx"

def verify_syntax(email):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))

def build_overpass_query(s, w, n, e, keyword):
    kw = (keyword or "").lower().strip()
    # category mapping
    if kw in ("restaurant", "food", "cafe", "pizza", "bakery"):
        filt = '["amenity"~"restaurant|cafe|fast_food|ice_cream"]'
    elif kw in ("salon", "saloon", "beauty", "barber", "spa"):
        filt = '["shop"~"beauty|hairdresser"]'
    elif kw in ("dentist", "dental", "clinic", "doctor", "hospital"):
        filt = '["amenity"~"dentist|doctors|clinic|hospital|pharmacy"]'
    elif kw in ("gym", "fitness", "yoga"):
        filt = '["amenity"~"gym"]'
    elif kw in ("hotel", "hostel", "stay"):
        filt = '["tourism"~"hotel|guest_house|hostel"]'
    elif kw in ("pharmacy", "medical"):
        filt = '["amenity"~"pharmacy"]'
    elif kw and kw not in ("all", "any", "shop", "business"):
        # generic: search name match + broad pois
        filt = ""
    else:
        filt = ""
    bbox = f"{s},{w},{n},{e}"
    if filt:
        q = f"""[out:json][timeout:25];
(
  nwr{filt}({bbox});
);
out center 60;"""
    else:
        q = f"""[out:json][timeout:25];
(
  nwr["shop"]({bbox});
  nwr["amenity"]({bbox});
  nwr["tourism"~"hotel|guest_house|hostel"]({bbox});
  nwr["office"]({bbox});
  nwr["craft"]({bbox});
);
out center 60;"""
    return q

def parse_elements(elements, keyword, max_n):
    leads = []
    kw = (keyword or "").lower()
    for el in elements:
        tags = el.get("tags", {}) or {}
        name = tags.get("name", "").strip()
        if not name:
            continue
        # keyword filter if custom
        if kw and kw not in ("all", "any", "shop", "business",
                             "restaurant", "food", "cafe", "salon", "dentist",
                             "gym", "hotel", "pharmacy", "clinic"):
            hay = f"{name} {tags.get('shop','')} {tags.get('amenity','')} {tags.get('cuisine','')}".lower()
            if kw not in hay:
                continue
        # drop chains
        if any(c in name.lower() for c in CHAIN_NAMES):
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        leads.append({
            "name": name,
            "category": tags.get("shop") or tags.get("amenity") or tags.get("tourism") or tags.get("craft") or tags.get("office") or "business",
            "address": ", ".join(filter(None, [tags.get("addr:housenumber", ""), tags.get("addr:street", ""),
                                                tags.get("addr:suburb", ""), tags.get("addr:city", "")])) or tags.get("addr:full", "") or "",
            "phone": tags.get("phone", "") or tags.get("contact:phone", "") or "",
            "website": tags.get("website", "") or tags.get("contact:website", "") or "",
            "opening_hours": tags.get("opening_hours", ""),
            "lat": lat, "lon": lon,
            "osm_type": el.get("type", ""),
            "osm_id": el.get("id", ""),
        })
        if len(leads) >= max_n:
            break
    # dedupe by name
    seen, uniq = set(), []
    for l in leads:
        k = l["name"].lower()
        if k not in seen:
            seen.add(k)
            uniq.append(l)
    return uniq

def crawl_emails(base_url):
    """Crawl home + contact/about pages for emails. Returns (emails, site_status, page_text_len)."""
    domain = extract_domain(base_url)
    if not domain:
        return [], "no-website", 0
    urls = [f"https://{domain}", f"https://{domain}/contact", f"https://{domain}/about",
            f"https://{domain}/contact-us", f"http://{domain}"]
    found, status, text_len = [], "dead", 0
    for u in urls[:5]:
        try:
            r = requests.get(u, headers=UA, timeout=8, allow_redirects=True)
            if r.status_code >= 400:
                continue
            status = "live"
            html = r.text or ""
            text_len = max(text_len, len(html))
            text = deobfuscate(html)
            found += EMAIL_RE.findall(text)
            if found and len(found) >= 3:
                break
            time.sleep(0.4)
        except Exception:
            continue
    return clean_emails(found), status, text_len

def duckduckgo_guess(name, area):
    """Free website guess via DuckDuckGo HTML. Returns url or ''."""
    try:
        q = quote_plus(f"{name} {area}")
        r = requests.get(f"https://html.duckduckgo.com/html/?q={q}",
                         headers=UA, timeout=10)
        if r.status_code != 200:
            return ""
        m = re.findall(r"uddg=([^\"&]+)", r.text)
        from urllib.parse import unquote
        for u in m:
            url = unquote(u)
            if any(b in url for b in ("duckduckgo", "facebook.com", "instagram.com",
                                      "justdial", "yelp.", "tripadvisor", "zomato")):
                continue
            if "." in url and " " not in url:
                return url[:120]
        return ""
    except Exception:
        return ""

def score_lead(has_site, site_status, text_len, phone, emails):
    score, reasons = 0, []
    if not has_site:
        score += 35; reasons.append("No website listed")
    if site_status == "dead" and has_site:
        score += 25; reasons.append("Website down/error")
    if site_status == "live" and 0 < text_len < 3000:
        score += 15; reasons.append("Thin site")
    if not phone:
        score += 10; reasons.append("No phone in listing")
    if not emails:
        score += 10; reasons.append("No email found")
    else:
        score += 5; reasons.append(f"{len(emails)} email(s) found")
    score += 5  # needs audit
    reasons.append("Needs speed/SEO audit")
    return min(score, 100), reasons

# ---------- routes ----------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/health")
def health():
    out = {"ok": True, "dns": HAS_DNS, "time": time.time()}
    if HAS_SGAI:
        try:
            out["sgai"] = sgai.credits()
        except Exception:
            out["sgai"] = {"enabled": False}
    else:
        out["sgai"] = {"enabled": False}
    return jsonify(out)

@app.route("/api/geocode")
def geocode():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "missing q"}), 400
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"format": "json", "q": q, "limit": 1},
                         headers=UA, timeout=12)
        j = r.json()
        if not j:
            return jsonify({"error": "area not found, try 'Bandra, Mumbai'"}), 404
        b = j[0]["boundingbox"]  # [s,n,w,e] as strings
        return jsonify({
            "display_name": j[0].get("display_name", q),
            "south": float(b[0]), "north": float(b[1]),
            "west": float(b[2]), "east": float(b[3]),
            "lat": float(j[0]["lat"]), "lon": float(j[0]["lon"]),
        })
    except Exception as ex:
        return jsonify({"error": f"geocode failed: {ex}"}), 502

@app.route("/api/search", methods=["POST"])
def search():
    data = request.get_json(force=True) or {}
    area = (data.get("area") or "").strip()
    keyword = (data.get("category") or data.get("keyword") or "all").strip() or "all"
    max_n = min(int(data.get("max", 40) or 40), 80)
    bbox = None
    # direct bbox or area->geocode
    if all(k in data for k in ("south", "west", "north", "east")):
        bbox = (float(data["south"]), float(data["west"]),
                float(data["north"]), float(data["east"]))
        display = area or "custom bbox"
    elif area:
        # shrink big city bbox to ~4km to avoid Overpass timeout
        try:
            g = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"format": "json", "q": area, "limit": 1},
                             headers=UA, timeout=12).json()
            if not g:
                return jsonify({"error": "area not found"}), 404
            lat, lon = float(g[0]["lat"]), float(g[0]["lon"])
            d = 0.02  # ~2km each side
            bbox = (lat - d, lon - d, lat + d, lon + d)
            display = g[0].get("display_name", area)
        except Exception as ex:
            return jsonify({"error": f"geocode failed: {ex}"}), 502
    else:
        return jsonify({"error": "provide area or bbox"}), 400

    s, w, n, e = bbox
    q = build_overpass_query(s, w, n, e, keyword)
    last_err = ""
    for mirror in OVERPASS_MIRRORS:
        try:
            r = requests.post(mirror, data={"data": q}, headers=UA, timeout=35)
            if r.status_code != 200:
                last_err = f"{mirror}: {r.status_code}"
                continue
            elements = r.json().get("elements", [])
            leads = parse_elements(elements, keyword, max_n)
            random.shuffle(leads)
            return jsonify({"area": display, "bbox": bbox, "count": len(leads), "leads": leads})
        except Exception as ex:
            last_err = f"{mirror}: {ex}"
            time.sleep(1)
    return jsonify({"error": f"Overpass busy, retry. {last_err}"}), 502

@app.route("/api/enrich", methods=["POST"])
def enrich():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    area = (data.get("area") or "").strip()
    website = (data.get("website") or "").strip()
    guessed = False
    if not website and name:
        website = duckduckgo_guess(name, area)
        guessed = bool(website)
    emails, site_status, text_len = [], "no-website", 0
    domain = extract_domain(website) if website else ""
    if website:
        emails, site_status, text_len = crawl_emails(website)
        # role-based fallback
        if domain and not emails:
            for local in ("info", "contact", "hello"):
                cand = f"{local}@{domain}"
                ok, _ = check_mx(domain)
                if ok:
                    emails = [cand + " (guessed)"]
                    break
    # verify first email MX
    mx_valid, mx_detail = (False, "no-domain")
    if emails:
        first = emails[0].replace(" (guessed)", "")
        dom = first.split("@")[-1] if "@" in first else ""
        mx_valid, mx_detail = check_mx(dom)
    has_site = bool(website)
    score, reasons = score_lead(has_site, site_status, text_len, data.get("phone", ""), emails)
    if guessed:
        reasons.insert(0, "Website auto-guessed via search")
    status_label = "no-website" if not has_site else ("dead-site" if site_status == "dead"
                  else ("thin-site" if text_len < 3000 else "has-website"))
    return jsonify({
        "name": name, "website": website, "guessed": guessed, "domain": domain,
        "emails": emails, "mx_valid": mx_valid, "mx_detail": mx_detail,
        "site_status": site_status, "status": status_label,
        "score": score, "reasons": reasons,
    })

@app.route("/api/ai-enrich", methods=["POST"])
def ai_enrich():
    """Hybrid AI enrich: ScrapeGraphAI cloud when keyed, else free fallback signal.

    Fires on hot leads only (caller decides). Costs ~5 credits (extract) plus
    ~6 if website discovery is needed. Never raises: always returns JSON with
    an `engine` field of 'ai' | 'free-fallback' | 'disabled'.
    """
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    area = (data.get("area") or "").strip()
    website = (data.get("website") or "").strip()
    phone = (data.get("phone") or "").strip()

    if not HAS_SGAI or not sgai.enabled():
        return jsonify({
            "engine": "disabled",
            "error": "SGAI_API_KEY not set. Set it server-side and restart.",
        }), 503

    credits_used, guessed = 0, False
    try:
        if not website and name:
            website = sgai.search_website(name, area)
            credits_used += 6
            guessed = bool(website)
        if not website:
            return jsonify({"engine": "ai", "name": name, "website": "",
                            "emails": [], "score": 60, "status": "no-website",
                            "reasons": ["AI found no website either — hottest lead"],
                            "credits_used": credits_used})
        profile = sgai.extract_lead(website)
        credits_used += 5
    except sgai.SGAICredits as ex:
        return jsonify({"engine": "free-fallback",
                        "error": f"AI credits exhausted ({ex}); used free pipeline"}), 429
    except sgai.SGAIError as ex:
        return jsonify({"engine": "free-fallback",
                        "error": f"AI failed ({ex}); used free pipeline"}), 502

    emails = clean_emails(profile.get("emails", []))
    domain = extract_domain(website)
    site_status = "live" if (emails or profile.get("services")) else "thin-site"
    mx_valid, mx_detail = (False, "no-domain")
    if emails:
        first = emails[0]
        mx_valid, mx_detail = check_mx(first.split("@")[-1] if "@" in first else "")
    if domain and not emails:
        for local in ("info", "contact", "hello"):
            ok, _ = check_mx(domain)
            if ok:
                emails = [f"{local}@{domain} (guessed)"]
                mx_valid, mx_detail = True, "role-guess"
                break

    score, reasons = score_lead(True, "live" if site_status == "live" else "dead",
                                5000, phone or ";".join(profile.get("phones", [])),
                                emails)
    ai_notes = []
    if profile.get("owner_name"):
        ai_notes.append(f"Owner: {profile['owner_name']}")
    if profile.get("has_booking"):
        ai_notes.append("Has online booking")
    if not profile.get("has_pricing"):
        ai_notes.append("No prices listed")
    if profile.get("whatsapp"):
        ai_notes.append("WhatsApp contact")
    if profile.get("services"):
        ai_notes.append(f"{len(profile['services'])} services found")
    if guessed:
        ai_notes.insert(0, "Website found by AI search")
    reasons = ai_notes + reasons

    status_label = "thin-site" if not emails else "has-website"
    return jsonify({
        "engine": "ai", "name": name, "website": website, "guessed": guessed,
        "domain": domain, "emails": emails, "mx_valid": mx_valid,
        "mx_detail": mx_detail, "site_status": site_status,
        "status": status_label, "score": score, "reasons": reasons,
        "ai_profile": {k: profile.get(k) for k in
                       ("owner_name", "services", "instagram", "facebook",
                        "whatsapp", "has_booking", "has_pricing", "summary")},
        "credits_used": credits_used,
    })

@app.route("/api/demo")
def demo():
    demo_leads = [
        {"name": "Glow Studio Salon", "category": "beauty", "address": "Linking Rd, Bandra, Mumbai",
         "phone": "", "website": "", "lat": 19.06, "lon": 72.82},
        {"name": "Sharma Dental Care", "category": "dentist", "address": "MG Road, Pune",
         "phone": "020-40001234", "website": "http://sharmadentalcare-example.in", "lat": 18.52, "lon": 73.85},
        {"name": "Iron Paradise Gym", "category": "gym", "address": "Sector 29, Gurgaon",
         "phone": "0124-1112233", "website": "", "lat": 28.46, "lon": 77.07},
        {"name": "Cafe Aroma", "category": "cafe", "address": "Koramangala, Bengaluru",
         "phone": "", "website": "https://cafearoma-example.com", "lat": 12.93, "lon": 77.61},
        {"name": "CityStay Guest House", "category": "guest_house", "address": "Paharganj, Delhi",
         "phone": "011-41550000", "website": "", "lat": 28.64, "lon": 77.21},
        {"name": "FreshBite Bakery", "category": "bakery", "address": "Anna Nagar, Chennai",
         "phone": "", "website": "", "lat": 13.08, "lon": 80.21},
    ]
    return jsonify({"area": "Demo — India sample", "count": len(demo_leads), "leads": demo_leads})

if __name__ == "__main__":
    import os as _os
    host = _os.environ.get("HOST", "127.0.0.1")  # HOST=0.0.0.0 to test from your phone on the same Wi-Fi
    port = int(_os.environ.get("PORT", "5000"))
    print(f"Local Business Gap Finder: http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
