#!/usr/bin/env python3
"""Build snowmap.json: gridded snowfall totals (24h, 48h, 3d, 7d, 14d) for the map.

Grid colors stay a model blend (NBM, ECMWF, GFS) because a weather.gov call per cell
is not practical. Headline table totals are the official NWS gridpoint, not this median.
Runs in GitHub Actions so phones never make thousands of forecast calls.
"""
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "snowmap.json")

MODELS = [("ncep_nbm_conus", "NBM"), ("ecmwf_ifs025", "ECMWF"), ("gfs_seamless", "GFS")]
WINDOWS = [("h24", 24), ("h48", 48), ("d3", 72), ("d7", 168), ("d14", 336)]
FORECAST_DAYS = 15  # 360 h: enough for a 14-day window starting at any hour today

# Each view has its own grid; regional views are sampled finer so the mountains show up.
VIEWS = [
    {"id": "west", "name": "West", "lon0": -125.0, "lon1": -102.0, "lat0": 31.0, "lat1": 49.5, "step": 0.5},
    {"id": "sanjuans", "name": "San Juans", "lon0": -109.4, "lon1": -105.6, "lat0": 36.6, "lat1": 38.7, "step": 0.15},
    {"id": "nco", "name": "N. CO / WY", "lon0": -109.0, "lon1": -104.6, "lat0": 39.3, "lat1": 42.0, "step": 0.15},
    {"id": "utid", "name": "UT / ID", "lon0": -117.6, "lon1": -110.0, "lat0": 40.4, "lat1": 46.0, "step": 0.25},
]

# Keep in sync with LOCATIONS in index.html. lat/lon here are the forecast lookup
# (fcLat/fcLon when set) so NWS/Open-Meteo match loc.ft; elevation is always metres of loc.m.
POINTS = [
    ("sharkstooth", 37.50356, -108.11405, 3271), ("sharkpeak", 37.4599, -108.0732, 3545),
    ("columbus", 37.4415, -108.0520, 3286), ("spud", 37.7108, -107.8104, 3249),
    ("molas", 37.74929, -107.68933, 3236), ("stump", 37.47647, -107.63348, 3423),
    ("purg", 37.6150, -107.8540, 3292), ("wolf", 37.4747, -106.7932, 3353),
    ("rabbit", 40.36735, -106.74118, 2862), ("nfrench", 41.33087, -106.37558, 3094),
    ("battle", 41.05402, -107.26674, 2274), ("tonygrove", 41.89833, -111.62957, 2576),
    ("deadwood", 44.54492, -115.56386, 2131), ("brundage", 45.0050, -116.1540, 2329),
    ("vailmtn", 39.61765, -106.38019, 3136), ("coppermtn", 39.4892, -106.2026, 3200),
    ("fremont", 39.38014, -106.19784, 3447), ("hoosier", 39.3609, -106.0289, 3536),
    ("grizzly", 39.64646, -105.86940, 3386), ("loveland", 39.67428, -105.90264, 3478),
    ("jackwhacker", 39.57096, -105.80355, 3362), ("elliot", 39.86380, -106.42473, 3216),
    ("redsand", 39.7350, -106.3920, 3048), ("vailpass", 39.5303, -106.2107, 3231),
    ("vail", 39.6055, -106.3680, 3429), ("copper", 39.4890, -106.1550, 3554),
    ("breck", 39.4482, -106.1096, 3914), ("keystone", 39.5297, -105.8813, 3780),
    ("abasin", 39.6360, -105.8512, 3795),
]

BATCH = 100
# A 100-point batch counts as ~107 calls; the free tier allows 600 calls/minute.
MIN_GAP_S = 12
_last_call = 0.0


def fetch(lats, lons, elevs=None):
    global _last_call
    wait = _last_call + MIN_GAP_S - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={','.join(f'{v:.3f}' for v in lats)}&longitude={','.join(f'{v:.3f}' for v in lons)}"
           + (f"&elevation={','.join(str(e) for e in elevs)}" if elevs else "")
           + f"&hourly=snowfall&models={','.join(m for m, _ in MODELS)}"
           f"&forecast_days={FORECAST_DAYS}&timezone=GMT&precipitation_unit=inch")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                data = json.load(r)
            return data if isinstance(data, list) else [data]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if attempt == 3 or (e.code == 429 and "daily" in body.lower()):
                raise RuntimeError(f"Open-Meteo HTTP {e.code}: {body}") from None
            if e.code == 429:
                time.sleep(65)
                continue
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 3:
                raise RuntimeError(f"Open-Meteo unreachable: {e}") from None
        time.sleep(5 * (attempt + 1))


def window_totals(rec, start):
    h = rec["hourly"]
    units = rec.get("hourly_units", {})
    out, used = {}, {}
    prev = 0.0
    for wid, hours in WINDOWS:
        totals, names = [], []
        for key, name in MODELS:
            arr = h.get(f"snowfall_{key}")
            if not arr:
                continue
            unit = units.get(f"snowfall_{key}", "inch")
            k = {"inch": 1, "in": 1, "cm": 1 / 2.54, "mm": 1 / 25.4}[unit]
            seg = arr[start:start + hours]
            if len(seg) == hours and all(v is not None for v in seg):
                totals.append(max(0.0, sum(seg)) * k)
                names.append(name)
        # Fewer models reach the longer windows, so the median can dip; a longer window
        # still can't hold less snow than a shorter one that starts at the same hour.
        val = max(statistics.median(totals), prev) if totals else None
        if val is not None:
            prev = val
        out[wid] = round(val, 1) if val is not None else None
        used[wid] = names
    return out, used


def start_index(rec, now):
    times = rec["hourly"]["time"]
    stamp = now.strftime("%Y-%m-%dT%H:00")
    return times.index(stamp) if stamp in times else 0


def main():
    now = datetime.now(timezone.utc)
    t0 = time.time()
    models_used = {}
    views = []
    for v in VIEWS:
        nx = int(round((v["lon1"] - v["lon0"]) / v["step"])) + 1
        ny = int(round((v["lat1"] - v["lat0"]) / v["step"])) + 1
        cells = [(v["lat0"] + j * v["step"], v["lon0"] + i * v["step"]) for j in range(ny) for i in range(nx)]
        grids = {wid: [] for wid, _ in WINDOWS}
        for b in range(0, len(cells), BATCH):
            chunk = cells[b:b + BATCH]
            recs = fetch([c[0] for c in chunk], [c[1] for c in chunk])
            for rec in recs:
                tot, used = window_totals(rec, start_index(rec, now))
                for wid, val in tot.items():
                    grids[wid].append(val)
                    if used[wid] and len(used[wid]) > len(models_used.get(wid, [])):
                        models_used[wid] = used[wid]
        views.append({"id": v["id"], "name": v["name"], "step": v["step"], "nx": nx, "ny": ny,
                      "lon0": v["lon0"], "lat0": v["lat0"],
                      "lon1": round(v["lon0"] + (nx - 1) * v["step"], 3), "lat1": round(v["lat0"] + (ny - 1) * v["step"], 3),
                      "grids": grids})
        print(f"{v['id']}: {nx}x{ny} = {nx * ny} points", file=sys.stderr)

    recs = fetch([p[1] for p in POINTS], [p[2] for p in POINTS], [p[3] for p in POINTS])
    points = {}
    for p, rec in zip(POINTS, recs):
        tot, _ = window_totals(rec, start_index(rec, now))
        points[p[0]] = tot

    # Each model's own terrain height at our spots (elevation=nan turns off Open-Meteo's downscaling),
    # so the page can show how far below the real ridge a model thinks the site sits.
    terrain = {p[0]: {} for p in POINTS}
    for key, name in MODELS:
        try:
            url = ("https://api.open-meteo.com/v1/forecast"
                   f"?latitude={','.join(f'{p[1]:.3f}' for p in POINTS)}&longitude={','.join(f'{p[2]:.3f}' for p in POINTS)}"
                   f"&elevation={','.join('nan' for _ in POINTS)}&daily=snowfall_sum&models={key}&forecast_days=1")
            time.sleep(2)
            with urllib.request.urlopen(url, timeout=60) as r:
                recs = json.load(r)
            for p, rec in zip(POINTS, recs if isinstance(recs, list) else [recs]):
                if rec.get("elevation") is not None:
                    terrain[p[0]][name] = round(rec["elevation"])
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"terrain for {name} skipped: {e}", file=sys.stderr)

    out = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start": now.strftime("%Y-%m-%dT%H:00:00Z"),
        "source": "Open-Meteo",
        "method": "Median of NBM, ECMWF and GFS window totals; models that don't reach the end of a window are left out. "
                  "Longer windows never show less than shorter ones. Table Next totals use the NWS gridpoint, not this map.",
        "models": models_used,
        "windows": [{"id": wid, "hours": hrs} for wid, hrs in WINDOWS],
        "views": views,
        "points": points,
        "terrain_m": terrain,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes) in {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
