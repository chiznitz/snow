#!/usr/bin/env python3
"""Build conditions.json: NWS Area Forecast Discussions and avalanche forecasts for every spot.

- NWS: api.weather.gov /points resolves each spot to its forecast office; the latest AFD with a
  forecast section is stored once per office (aviation/fire/marine sections dropped).
- Avalanche: api.avalanche.org map-layer polygons locate each spot's zone (point in polygon, so
  it follows CAIC's switch from the early-season statewide zone to regional zones); the latest
  product for that zone is stored once per zone. Early season is reported as "no forecast yet".
Text is the forecasters' own words, lightly cleaned; nothing is paraphrased.
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snowmap import POINTS  # noqa: E402  (same spot list as the map)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "conditions.json")
UA = "chiznitz-snow (github.com/chiznitz/snow)"
NWS_HEADERS = {"User-Agent": UA, "Accept": "application/geo+json"}
OFFICE_NAMES = {"GJT": "Grand Junction", "BOU": "Boulder / Denver", "PUB": "Pueblo", "CYS": "Cheyenne",
                "RIW": "Riverton", "SLC": "Salt Lake City", "BOI": "Boise", "PIH": "Pocatello", "MSO": "Missoula"}
PREFERRED = ["LONG TERM", "EXTENDED", "DISCUSSION", "KEY MESSAGES", "SHORT TERM"]
DROP_SECTIONS = ("AVIATION", "FIRE WEATHER", "MARINE", "HYDROLOGY", "CLIMATE", "EQUIPMENT", "PRELIMINARY POINT")
ADMIN = re.compile(r"\b(warnings?|advisor(y|ies)|headlines?|no changes|on track|previous discussion|see .* for details)\b", re.I)


def get(url, headers=None):
    err = None
    for attempt in range(4):
        if attempt:
            time.sleep(1.2 * (2 ** (attempt - 1)))
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            err = e
            code = getattr(e, "code", None)
            if code and code < 500 and code != 429:
                break
    raise err


# ---------------- NWS ----------------

def sections(text):
    out, order, name, buf = {}, [], None, []
    for line in text.splitlines():
        m = re.match(r"^\.([A-Za-z][A-Za-z0-9 /&\-\(\)\.,']*?)\.{3}\s*(.*)$", line)
        if m:
            if name:
                out[name] = "\n".join(buf)
            name = re.sub(r"\s*(/.*|,\s*Issued.*)$", "", m.group(1), flags=re.I).strip().upper()
            buf = [m.group(2)]
            order.append(name)
        elif line.strip() == "&&":
            if name:
                out[name] = "\n".join(buf)
            name, buf = None, []
        elif name:
            buf.append(line)
    if name:
        out[name] = "\n".join(buf)
    return [(n, out[n]) for n in order if n in out]


def paragraphs(body):
    paras = []
    for p in re.split(r"\n\s*\n", body):
        p = re.sub(r"\s+", " ", p).strip()
        p = re.sub(r"^Issued \d{3,4} [AP]M \w+ \w+ \w+ \d+ \d{4}\s*", "", p)
        p = re.sub(r"\s*-\s*[A-Z]{2,3}$|\s*\.\.\.\s*[A-Za-z]+$", "", p)
        if len(p) > 40:
            paras.append(p)
    return paras


def one_line(text, limit=260):
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        if out and len(out) + len(s) + 1 > limit:
            break
        out = (out + " " + s).strip()
    return out or text[:limit].rsplit(" ", 1)[0] + "…"


def extended_paragraph(paras):
    for p in reversed(paras):
        if len(p) >= 120 and not (len(p) < 300 and ADMIN.search(p)):
            return p
    return paras[-1]


def afd_for(code):
    listing = get(f"https://api.weather.gov/products/types/AFD/locations/{code}", NWS_HEADERS)
    for item in listing.get("@graph", [])[:6]:
        prod = get(item["@id"], NWS_HEADERS)
        secs = [(n, paragraphs(b)) for n, b in sections(prod.get("productText", "")) if not n.startswith(DROP_SECTIONS)]
        secs = [(n, p) for n, p in secs if p and "WATCHES" not in n]
        if not secs:
            continue
        pick = next((p for want in PREFERRED for n, p in secs if n.startswith(want)), None)
        return {
            "office": code, "name": OFFICE_NAMES.get(code, code), "issued": prod["issuanceTime"],
            "excerpt": one_line(extended_paragraph(pick)) if pick else "",
            "sections": [{"name": n.title(), "paragraphs": p} for n, p in secs],
            "url": f"https://forecast.weather.gov/product.php?site=NWS&issuedby={code}&product=AFD&format=txt",
        }
    raise RuntimeError(f"{code}: none of the recent AFDs had a forecast section")


def nws(errors):
    spots, offices = {}, {}
    for pid, lat, lon, _ in POINTS:
        try:
            spots[pid] = get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}", NWS_HEADERS)["properties"]["cwa"]
        except Exception as e:
            errors.append(f"nws points {pid}: {type(e).__name__}: {e}")
    for code in sorted(set(spots.values())):
        try:
            offices[code] = afd_for(code)
            print(f"NWS {code}: {offices[code]['excerpt'][:70]}…", file=sys.stderr)
        except Exception as e:
            errors.append(f"nws afd {code}: {type(e).__name__}: {e}")
    return {"spots": spots, "offices": offices}


# ---------------- Avalanche ----------------

def html_text(s):
    if not s:
        return []
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|li|h\d|ul|ol)>", "\n\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "• ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", s) if p.strip()]


def point_in(lon, lat, geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        ring, inside = poly[0], False
        for i in range(len(ring)):
            x1, y1 = ring[i][:2]
            x2, y2 = ring[(i + 1) % len(ring)][:2]
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-12) + x1:
                inside = not inside
        if inside:
            return True
    return False


def problem(p):
    locs = p.get("location") or []
    return {
        "name": p.get("name"), "likelihood": p.get("likelihood"), "size": p.get("size") or [],
        "aspects_elevations": locs,
        "discussion": html_text(p.get("discussion")),
    }


def avalanche(errors):
    layer = get("https://api.avalanche.org/v2/public/products/map-layer")
    feats = layer.get("features", [])
    spots, zones = {}, {}
    for pid, lat, lon, _ in POINTS:
        hit = next((f for f in feats if point_in(lon, lat, f["geometry"])), None)
        spots[pid] = str(hit["id"]) if hit else None
        if hit and str(hit["id"]) not in zones:
            pr = hit["properties"]
            zones[str(hit["id"])] = {
                "zone_id": hit["id"], "zone_name": pr.get("name"), "center_id": pr.get("center_id"),
                "center_name": pr.get("center"), "center_url": pr.get("center_link"), "zone_url": pr.get("link"),
                "off_season": pr.get("off_season"), "map_danger": pr.get("danger"), "map_danger_level": pr.get("danger_level"),
                "travel_advice": pr.get("travel_advice"), "season_start": pr.get("start_date"), "season_end": pr.get("end_date"),
            }
    now = datetime.now(timezone.utc)
    for zid, z in zones.items():
        try:
            p = get(f"https://api.avalanche.org/v2/public/product?type=forecast&center_id={z['center_id']}&zone_id={zid}")
            if not isinstance(p, dict) or not p.get("published_time"):
                z["product"] = None
                continue
            expires = p.get("expires_time")
            expired = bool(expires) and datetime.fromisoformat(expires.replace("Z", "+00:00")) < now
            danger = [d for d in (p.get("danger") or []) if any(d.get(k) not in (None, -1, 0) for k in ("lower", "middle", "upper"))]
            z["product"] = {
                "id": p.get("id"), "type": p.get("product_type"), "status": p.get("status"),
                "published": p.get("published_time"), "expires": expires, "expired": expired, "author": p.get("author"),
                "zones": [fz.get("name") for fz in (p.get("forecast_zone") or [])],
                "danger": p.get("danger") or [],
                "has_rating": bool(danger) and not expired,
                "problems": [problem(x) for x in (p.get("forecast_avalanche_problems") or [])],
                "bottom_line": html_text(p.get("bottom_line")),
                "hazard_discussion": html_text(p.get("hazard_discussion")),
                "weather_discussion": html_text(p.get("weather_discussion")),
                "announcement": html_text(p.get("announcement")),
                "url": next((fz.get("url") for fz in (p.get("forecast_zone") or []) if str(fz.get("id")) == zid), None) or z["zone_url"],
            }
            print(f"AVY {z['center_id']} {z['zone_name']}: {z['product']['type']} {z['product']['published'][:10]} rating={z['product']['has_rating']}", file=sys.stderr)
        except Exception as e:
            z["product"] = None
            errors.append(f"avalanche {z['center_id']} zone {zid}: {type(e).__name__}: {e}")
    return {"spots": spots, "zones": zones, "map_url": "https://avalanche.org/"}


def main():
    errors = []
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        out["nws"] = nws(errors)
    except Exception as e:
        errors.append(f"nws: {type(e).__name__}: {e}")
    try:
        out["avalanche"] = avalanche(errors)
    except Exception as e:
        errors.append(f"avalanche: {type(e).__name__}: {e}")
    out["errors"] = errors
    for err in errors:
        print(err, file=sys.stderr)

    old = {}
    if os.path.exists(OUT):
        try:
            with open(OUT) as f:
                old = json.load(f)
        except (OSError, ValueError):
            old = {}
    # Keep last good data for anything that failed this run.
    for key in ("nws", "avalanche"):
        if key not in out and key in old:
            out[key] = old[key]
    cmp_old, cmp_new = dict(old), dict(out)
    cmp_old.pop("generated_at", None)
    cmp_new.pop("generated_at", None)
    if cmp_old == cmp_new:
        print("conditions.json unchanged", file=sys.stderr)
        return
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
