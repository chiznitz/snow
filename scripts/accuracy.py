#!/usr/bin/env python3
"""Daily NWS forecast + SNOTEL observation snapshots for the accuracy page.

Forecast points match index.html (fcLat/fcLon when set). Only SNOTEL stations
are stored. NWS snowfallAmount is the snow total; quantitativePrecipitation is
the liquid/SWE-like QPF. Observed SNWD and WTEQ come from NRCS AWDB hourly.
"""
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
FORECAST_OUT = os.path.join(DATA, "forecast-history.json")
OBSERVED_OUT = os.path.join(DATA, "observed-history.json")
UA = "chiznitz-snow (github.com/chiznitz/snow)"
HOUR = 3600 * 1000
DENVER = ZoneInfo("America/Denver")

# Keep in sync with SNOTEL rows in index.html. lat/lon are the NWS lookup
# (fcLat/fcLon when the page sets them so the cell matches station elevation).
STATIONS = [
    {"id": "sharkstooth", "name": "Sharkstooth", "triplet": "1060:CO:SNTL", "lat": 37.50356, "lon": -108.11405},
    {"id": "columbus", "name": "Columbus Basin", "triplet": "904:CO:SNTL", "lat": 37.4415, "lon": -108.0520},
    {"id": "spud", "name": "Spud Mountain", "triplet": "780:CO:SNTL", "lat": 37.7108, "lon": -107.8104},
    {"id": "molas", "name": "Molas Pass", "triplet": "632:CO:SNTL", "lat": 37.74929, "lon": -107.68933},
    {"id": "stump", "name": "Stump Lakes", "triplet": "797:CO:SNTL", "lat": 37.47647, "lon": -107.63348},
    {"id": "rabbit", "name": "Rabbit Ears", "triplet": "709:CO:SNTL", "lat": 40.36735, "lon": -106.74118},
    {"id": "nfrench", "name": "North French Creek", "triplet": "668:WY:SNTL", "lat": 41.33087, "lon": -106.37558},
    {"id": "battle", "name": "Battle Mountain", "triplet": "317:WY:SNTL", "lat": 41.05402, "lon": -107.26674},
    {"id": "tonygrove", "name": "Tony Grove Lake", "triplet": "823:UT:SNTL", "lat": 41.89833, "lon": -111.62957},
    {"id": "deadwood", "name": "Deadwood Summit", "triplet": "439:ID:SNTL", "lat": 44.54492, "lon": -115.56386},
    {"id": "brundage", "name": "Brundage Mountain", "triplet": "370:ID:SNTL", "lat": 45.0050, "lon": -116.1540,
     "note": "Forecast at the summit; SNOTEL is Brundage Reservoir (6,280 ft)."},
]
WINDOWS = (("n24", "qpf24", 24), ("n72", "qpf72", 72), ("n7", "qpf7", 168))


def get(url, tries=4, headers=None):
    hdrs = {"User-Agent": UA}
    if headers:
        hdrs.update(headers)
    err = None
    for attempt in range(tries):
        if attempt:
            time.sleep(1.2 * (2 ** (attempt - 1)))
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as e:
            err = e
            code = getattr(e, "code", None)
            if code and code < 500 and code != 429:
                break
    raise err


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
        f.write("\n")
    os.replace(tmp, path)


def iso(ms=None):
    if ms is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000


def denver_day(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(DENVER).strftime("%Y-%m-%d")


DUR_RE = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")


def parse_iso_duration(s):
    m = DUR_RE.match(s or "")
    if not m:
        return float("nan")
    return ((int(m[1] or 0) * 86400) + (int(m[2] or 0) * 3600) + (int(m[3] or 0) * 60) + float(m[4] or 0)) * 1000


def nws_to_inches(v, uom):
    u = str(uom or "").lower()
    return v if ("inch" in u or u.endswith(":in")) else v / 25.4


def nws_hourly_inches(sa):
    buckets = {}
    if not sa:
        return buckets
    for row in sa.get("values") or []:
        if row.get("value") is None or not math.isfinite(row["value"]):
            continue
        parts = str(row["validTime"]).split("/")
        if len(parts) != 2:
            continue
        start = datetime.fromisoformat(parts[0].replace("Z", "+00:00")).timestamp() * 1000
        ms = parse_iso_duration(parts[1])
        if not math.isfinite(start) or not math.isfinite(ms) or ms <= 0:
            continue
        end = start + ms
        total = max(0.0, nws_to_inches(row["value"], sa.get("uom")))
        t = start
        while t < end - 1:
            hour_start = math.floor(t / HOUR) * HOUR
            nxt = min(hour_start + HOUR, end)
            buckets[hour_start] = buckets.get(hour_start, 0) + total * (nxt - t) / ms
            t = nxt
    return buckets


def nws_sum_range(hours, frm, to):
    if not hours or to <= frm:
        return None
    s, seen = 0.0, False
    t = math.floor(frm / HOUR) * HOUR
    while t < to:
        v = hours.get(t)
        if v is not None:
            a, b = max(t, frm), min(t + HOUR, to)
            if b > a:
                s += v * (b - a) / HOUR
                seen = True
        t += HOUR
    return s if seen else None


def awdb(ms):
    return (datetime.fromtimestamp(ms / 1000, timezone.utc) - timedelta(hours=8)).strftime("%Y-%m-%d %H:00")


def snapshot_forecasts(now_ms, errors):
    spots = {}
    nws_h = {"Accept": "application/geo+json"}
    for st in STATIONS:
        try:
            pts = get(f"https://api.weather.gov/points/{st['lat']:.4f},{st['lon']:.4f}", headers=nws_h)
            pr = pts.get("properties") or {}
            grid_url = pr.get("forecastGridData")
            if not grid_url:
                raise RuntimeError("no forecastGridData")
            grid = get(grid_url, headers=nws_h)
            gp = grid.get("properties") or {}
            snow = nws_hourly_inches(gp.get("snowfallAmount"))
            qpf = nws_hourly_inches(gp.get("quantitativePrecipitation"))
            row = {
                "name": st["name"],
                "triplet": st["triplet"],
                "grid": f"{pr.get('gridId')} {pr.get('gridX')},{pr.get('gridY')}" if pr.get("gridId") is not None else "",
                "nws_update": gp.get("updateTime"),
            }
            if st.get("note"):
                row["note"] = st["note"]
            for snow_k, qpf_k, hours in WINDOWS:
                row[snow_k] = nws_sum_range(snow, now_ms, now_ms + hours * HOUR)
                row[qpf_k] = nws_sum_range(qpf, now_ms, now_ms + hours * HOUR)
            spots[st["id"]] = row
        except Exception as e:
            errors.append(f"nws {st['id']}: {type(e).__name__}: {e}")
        time.sleep(0.35)
    return spots


def fetch_observed(now_ms, errors):
    try:
        url = (
            "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
            f"?stationTriplets={','.join(s['triplet'] for s in STATIONS)}"
            "&elements=SNWD,WTEQ&duration=HOURLY"
            f"&beginDate={urllib.request.quote(awdb(now_ms - 14 * 24 * HOUR))}"
            f"&endDate={urllib.request.quote(awdb(now_ms + HOUR))}"
        )
        data = get(url)
        if not isinstance(data, list) or not data:
            raise RuntimeError("no stations")
        return data
    except Exception as e:
        errors.append(f"snotel: {type(e).__name__}: {e}")
        return None


def series_from_awdb(rec):
    out = {}
    for el in rec.get("data") or []:
        code = (el.get("stationElement") or {}).get("elementCode")
        if code not in ("SNWD", "WTEQ"):
            continue
        for v in el.get("values") or []:
            if v.get("value") is None:
                continue
            # AWDB timestamps are Pacific Standard Time year-round (UTC−8).
            raw = v["date"]
            day, hhmm = (raw.split(" ") + ["00:00"])[:2]
            y, m, d = map(int, day.split("-"))
            hh, mm = map(int, hhmm.split(":")[:2])
            t = datetime(y, m, d, hh, mm, tzinfo=timezone.utc) + timedelta(hours=8)
            key = int(t.timestamp() // 3600 * 3600) * 1000
            row = out.setdefault(key, {"t": iso(key)})
            if code == "SNWD":
                row["depth"] = float(v["value"])
            else:
                row["swe"] = float(v["value"])
    return [out[k] for k in sorted(out)]


def merge_observed(old, awdb_rows):
    by_id = {s["id"]: s for s in STATIONS}
    by_triplet = {s["triplet"]: s["id"] for s in STATIONS}
    stations = old.get("stations") or {}
    if awdb_rows:
        for rec in awdb_rows:
            sid = by_triplet.get(rec.get("stationTriplet"))
            if not sid:
                continue
            st = by_id[sid]
            bucket = stations.setdefault(sid, {"name": st["name"], "triplet": st["triplet"], "series": []})
            have = {p["t"]: p for p in bucket.get("series") or []}
            for p in series_from_awdb(rec):
                have[p["t"]] = {**have.get(p["t"], {}), **p}
            series = [have[k] for k in sorted(have)]
            cutoff = iso(int(time.time() * 1000) - 400 * 24 * HOUR)
            bucket["series"] = [p for p in series if p["t"] >= cutoff]
    return stations


def main():
    now_ms = int(time.time() * 1000)
    issued = iso(now_ms)
    errors = []

    spots = snapshot_forecasts(now_ms, errors)
    awdb_rows = fetch_observed(now_ms, errors)

    fc = load_json(FORECAST_OUT, {"started": None, "snapshots": []})
    if not fc.get("started") and spots:
        fc["started"] = issued
    day = denver_day(now_ms)
    snap = {"issued": issued, "spots": spots}
    kept = []
    replaced = False
    for prev in fc.get("snapshots") or []:
        try:
            same = denver_day(parse_iso(prev["issued"])) == day
        except Exception:
            same = False
        if same:
            kept.append(snap)
            replaced = True
        else:
            kept.append(prev)
    if not replaced:
        kept.append(snap)
    fc["snapshots"] = kept
    fc["updated"] = issued
    if errors:
        fc["errors"] = errors
    else:
        fc.pop("errors", None)
    save_json(FORECAST_OUT, fc)

    obs = load_json(OBSERVED_OUT, {"stations": {}})
    obs["stations"] = merge_observed(obs, awdb_rows)
    obs["updated"] = issued
    if errors:
        obs["errors"] = [e for e in errors if e.startswith("snotel")]
        if not obs["errors"]:
            obs.pop("errors", None)
    else:
        obs.pop("errors", None)
    save_json(OBSERVED_OUT, obs)

    n_spots = len(spots)
    n_obs = sum(len((obs["stations"].get(s["id"]) or {}).get("series") or []) for s in STATIONS)
    print(f"issued {issued} · {n_spots}/{len(STATIONS)} forecasts · {n_obs} observed hours")
    if errors:
        print("errors:")
        for e in errors:
            print(" ", e)
        # Still a useful run if we got most stations.
        if n_spots < len(STATIONS) / 2 and not awdb_rows:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
