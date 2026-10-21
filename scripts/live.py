#!/usr/bin/env python3
"""Build live.json: a server-side snapshot of everything the page otherwise fetches live.

The browser renders from this file first (same-origin, fast, never rate-limited) and only then
tries the live APIs. Phones on carrier NAT share one public IP with thousands of users, so
Open-Meteo's per-IP limits and NRCS's firewall can both fail for them; this keeps the page usable.
URLs here must match the ones in index.html so the page can parse the snapshot with the same code.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snowmap import POINTS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "live.json")
UA = "chiznitz-snow (github.com/chiznitz/snow)"
MODELS = "ecmwf_ifs025,gfs_seamless,icon_seamless,gem_seamless,ukmo_seamless,jma_seamless,ncep_hrrr_conus,ncep_nam_conus"
TRIPLETS = ["1060:CO:SNTL", "904:CO:SNTL", "780:CO:SNTL", "632:CO:SNTL", "797:CO:SNTL", "709:CO:SNTL",
            "668:WY:SNTL", "317:WY:SNTL", "823:UT:SNTL", "439:ID:SNTL", "370:ID:SNTL"]


def get(url, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))


def awdb(ms):
    # AWDB wants Pacific Standard Time (UTC-8, no DST), formatted "YYYY-MM-DD HH:00".
    return (datetime.fromtimestamp(ms / 1000, timezone.utc) - timedelta(hours=8)).strftime("%Y-%m-%d %H:00")


def main():
    now_ms = int(time.time() * 1000)
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "forecast": {}, "errors": []}

    for pid, lat, lon, m in POINTS:
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={lat}&longitude={lon}&elevation={m}"
               "&daily=snowfall_sum,rain_sum,temperature_2m_max,temperature_2m_min"
               f"&models={MODELS}"
               "&forecast_days=16&timezone=America%2FDenver&precipitation_unit=inch&temperature_unit=fahrenheit")
        try:
            j = get(url)
            if j.get("error") or not j.get("daily", {}).get("time"):
                raise RuntimeError(j.get("reason") or "no daily data")
            out["forecast"][pid] = j
        except Exception as e:
            out["errors"].append(f"forecast {pid}: {type(e).__name__}: {e}")
        time.sleep(1.2)

    try:
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={','.join(str(p[1]) for p in POINTS)}&longitude={','.join(str(p[2]) for p in POINTS)}"
               f"&elevation={','.join(str(p[3]) for p in POINTS)}"
               "&hourly=snowfall,wind_speed_700hPa,wind_direction_700hPa&past_days=3&forecast_days=10"
               "&timezone=America%2FDenver&wind_speed_unit=mph&precipitation_unit=inch")
        w = get(url)
        if not isinstance(w, list) or len(w) != len(POINTS):
            raise RuntimeError("incomplete wind response")
        out["wind"] = w
    except Exception as e:
        out["errors"].append(f"wind: {type(e).__name__}: {e}")

    # Hourly snowfall/temperature for the table's 24/48/72h-from-now windows (HOURLY_URL in index.html).
    try:
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={','.join(str(p[1]) for p in POINTS)}&longitude={','.join(str(p[2]) for p in POINTS)}"
               f"&elevation={','.join(str(p[3]) for p in POINTS)}"
               "&hourly=snowfall,temperature_2m"
               "&models=ecmwf_ifs025,gfs_seamless,icon_seamless,gem_seamless,ukmo_seamless,jma_seamless,ncep_hrrr_conus"
               "&past_days=1&forecast_days=4&timezone=America%2FDenver&precipitation_unit=inch&temperature_unit=fahrenheit")
        h = get(url)
        if not isinstance(h, list) or len(h) != len(POINTS):
            raise RuntimeError("incomplete hourly response")
        out["hourly"] = h
    except Exception as e:
        out["errors"].append(f"hourly: {type(e).__name__}: {e}")

    try:
        url = ("https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
               f"?stationTriplets={','.join(TRIPLETS)}&elements=SNWD,WTEQ&duration=HOURLY"
               f"&beginDate={urllib.request.quote(awdb(now_ms - 170 * 3600 * 1000))}&endDate={urllib.request.quote(awdb(now_ms + 3600 * 1000))}")
        s = get(url)
        if not isinstance(s, list) or not s:
            raise RuntimeError("no stations")
        out["snotel"] = s
    except Exception as e:
        out["errors"].append(f"snotel: {type(e).__name__}: {e}")

    # Keep the previous snapshot's section if a source failed this run; the page shows its age.
    if os.path.exists(OUT):
        try:
            with open(OUT) as f:
                old = json.load(f)
            for key in ("wind", "hourly", "snotel"):
                if key not in out and key in old:
                    out[key] = old[key]
                    out.setdefault("stale", {})[key] = old.get("generated_at")
            for pid in old.get("forecast", {}):
                if pid not in out["forecast"]:
                    out["forecast"][pid] = old["forecast"][pid]
                    out.setdefault("stale", {})["forecast:" + pid] = old.get("generated_at")
        except (OSError, ValueError):
            pass

    for err in out["errors"]:
        print(err, file=sys.stderr)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes): {len(out['forecast'])} forecasts, wind={'wind' in out}, hourly={'hourly' in out}, snotel={'snotel' in out}", file=sys.stderr)


if __name__ == "__main__":
    main()
