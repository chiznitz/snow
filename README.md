# snow

Phone-first snow dashboard centered on Durango, CO: https://chiznitz.github.io/snow/

Static HTML/CSS/vanilla JS, no build step, no API keys. GitHub Pages serves `index.html` from the root of `main`.

Sites are defined in the `REGIONS` / `LOCATIONS` arrays in `index.html`. Each location gets one card with a snowpack panel (if it has a SNOTEL triplet) and a forecast panel, plus a row in the "At a glance" table.

- **Snowpack:** NRCS SNOTEL AWDB REST API, hourly SNWD/WTEQ.
- **Forecast:** the headline totals (next 24h / 48h / 72h and the first week) are the official NWS gridpoint
  snowfall forecast for each point (api.weather.gov). Days the NWS grid does not cover (usually 8–14) come from
  Open-Meteo's NBM, or ECMWF where NBM does not reach. The range under each total is NWS, NBM, ECMWF, GFS and
  HRRR (HRRR to ~48h), all from Open-Meteo's 16-day daily forecast downscaled to each site's elevation.
- **Loading and fallback:** `.github/workflows/live.yml` runs `scripts/live.py` every 2 hours and writes
  `live.json`, a snapshot of the exact SNOTEL (last 170 h), daily forecast, NWS gridpoint, hourly forecast and
  700 mb wind responses the page would fetch itself.
  The page renders from that snapshot first (same origin, ~80 KB gzipped), so it is readable before any
  third-party request is sent, then updates progressively: SNOTEL and NWS are always refreshed live; Open-Meteo
  is only called live when the snapshot is more than 3 hours old or you tap refresh (the cron is every 2 hours,
  but GitHub starts it up to ~50 minutes late, so a 2-hour window left most visitors making their own calls).
  Those live calls are batched: one Open-Meteo request carries every spot's coordinates (the same for the hourly
  and wind calls), so a page load is a handful of calls rather than one per spot, which is what used to trip the
  per-IP burst limit for everyone sharing a carrier address. Every third-party request has an 8 s timeout and one
  retry, and a failure falls back to the newer of the last good response saved in the browser or the snapshot,
  with a yellow "Live data unavailable" note on the affected card. No single fetch can block the page, and
  non-critical build steps are wrapped so one failure can't blank it. When you add a location, add its SNOTEL
  triplet to `TRIPLETS` in `scripts/live.py` too.
- **Chris Tomer:** `.github/workflows/tomer.yml` runs `scripts/tomer.py` hourly through late morning Mountain Time
  and on manual dispatch. It reads his channel RSS, takes the newest daily forecast video, and writes `tomer.json`
  from Tomer's own video description (YouTube blocks caption fetches from GitHub runners). Optional repo secrets
  `YT_PROXY_URL` or `YT_COOKIES` if you want the runner to retry captions.
- **Snowfall map:** `.github/workflows/snowmap.yml` runs `scripts/snowmap.py` twice a day (11:40 and 23:40 UTC)
  and on manual dispatch. It samples Open-Meteo's hourly snowfall (median of NBM, ECMWF and GFS) on a grid for
  each map area (West at 0.5°, San Juans and N. CO / WY at 0.15°, Summit / I-70 at 0.05°, UT / ID at 0.25°) and
  writes 24h / 48h / 3d / 7d / 14d totals to `snowmap.json`, plus totals at each location's own elevation for
  the yellow numbers. The map opens on the San Juans view for first-time visitors; a saved choice wins, and a
  first visit with starred spots opens on the area most of them are in. Opening a region or a spot's card moves
  the map to that spot's area (unless the reader chose the West view); the area buttons are the only thing that
  saves a choice. Where spots pile up at a zoom (the 15 Summit spots seen from N. CO / WY), the map keeps the
  biggest total per cluster and says how many are hidden. The page draws the field on a canvas over Esri World
  Imagery tiles with state lines from `borders.json`. A run is about 3,900 points, under half of Open-Meteo's
  free 10k daily calls. When you add a location, add it to `POINTS` in the script too, and give its region a
  view in `REGION_VIEW` in `index.html` if it needs one.
- **Snow forecast table:** one row per spot: Now (SNOTEL depth), Past (net depth change over the trailing 24h /
  48h / 72h / 7d from SNOTEL hourly, so settling means new snow is usually more than shown) and Next (forecast
  consensus for the next 24h / 48h / 72h / 7d / 14d, the same windows as the map). 24–72h are summed from the hour
  after now using one hourly Open-Meteo request for all 13 spots and the six global models (HRRR stored alongside);
  7d and 14d come from the daily forecast. A window only counts when at least two models cover it (`MIN_MODELS`),
  so a lone long-range model can't pose as the consensus. Zeros are blank dots; non-zero cells are colored pills
  with the model range underneath. Below 760px a SNOTEL / Forecast toggle picks which group shows, and the
  toggle, both header rows and the region rows stay on screen while the rows scroll (the card stops being a
  horizontal scroll container there, since the table fits the screen); tap a header to sort. Tap a row to open
  that spot's card inline (one at a time); region rows collapse (San Juans open by default, remembered per
  device). `#loc-<id>` in the URL opens that card on load.
  **Favorites:** the ☆ on a row or card pins that spot into a "My spots" group at the top of the table (rows
  move there rather than copy, so each spot's card stays unique). The list is saved on the device
  (`snowFavs`); `?fav=purg,wolf` in a shared link adds those spots on another device. A starred Summit spot
  loads that region's data on page load, and a first visit with starred spots starts the webcams on the first
  starred resort that has one.
  The card's 24H / 48H / 72H / 7D / 14D control drives one chart: hourly bars (median of the global models, faint
  model band, HRRR line, temperature, 700 mb wind arrows) with the SNOTEL depth trace for the same span to the left
  of "now", or the daily bars for 7D / 14D. Above the chart: one total and a High / Medium / Low confidence chip
  (model count and spread; the raw range is in the chip's tooltip and under "Model by model"), then a one-line
  model-agreement sentence. Snowpack shows depth with 24h / 7d change, SWE as a small line, and a 7-day trace.
- **Conditions (NWS + avalanche):** `.github/workflows/conditions.yml` runs `scripts/conditions.py` every 6 hours
  and writes `conditions.json`. NWS: api.weather.gov `/points` resolves each spot to its forecast office and the
  latest Area Forecast Discussion is stored once per office (aviation/fire/marine sections dropped). Avalanche:
  api.avalanche.org's map layer locates each spot's zone by point-in-polygon (so CAIC's early-season statewide zone
  and the regional zones that replace it on Nov 1 both work) and stores the latest product per zone with danger by
  elevation band, problems, aspects and discussion. Each card shows these as expandable sections; early season
  shows "No avalanche forecast issued yet". Deadwood Summit has no avalanche center.
- **Wind loading:** per card, an estimate from Open-Meteo hourly 700 mb wind (one batched request, client side):
  the snowfall-weighted mean wind during the last 72 h of snow and during the next storm, the lee aspects
  (opposite the wind), and a cross-check against any wind-slab problem the avalanche center lists. The card shows
  one line (loaded aspects, wind, storm) with the full sentences and the cross-check under "Details".
- **Webcams:** still images (cache-busted every 5 min) with optional live players, defined in `WEBCAMS` in
  `index.html`. Purgatory and Wolf Creek use Brownrice, Telluride uses ipcamlive, Grand Targhee uses SeeJH stills
  (its streams block embedding), Brundage serves its own JPGs, and I-70 Vail Pass uses public COtrip stills
  (`cocam.carsprogram.org/Snapshots/…`). Purgatory's Verkada base stream is locked to purgatory.ski, so it is
  linked rather than embedded.

| Region | Location | SNOTEL |
|---|---|---|
| San Juans | Sharkstooth | 1060:CO:SNTL |
| San Juans | Columbus Basin | 904:CO:SNTL |
| San Juans | Spud Mountain | 780:CO:SNTL |
| San Juans | Molas Pass | 632:CO:SNTL (Molas Lake) |
| San Juans | Stump Lakes | 797:CO:SNTL |
| San Juans | Purgatory | forecast only |
| San Juans | Wolf Creek | forecast only |
| Northern Colorado | Rabbit Ears | 709:CO:SNTL |
| Wyoming | North French Creek | 668:WY:SNTL |
| Wyoming | Battle Mountain | 317:WY:SNTL |
| Utah | Tony Grove Lake | 823:UT:SNTL |
| Idaho | Deadwood Summit | 439:ID:SNTL |
| Idaho | Brundage Mountain (summit forecast) | 370:ID:SNTL (Brundage Reservoir) |
| Summit County & Vail | Vail Mountain | 842:CO:SNTL |
| Summit County & Vail | Copper Mountain | 415:CO:SNTL |
| Summit County & Vail | Fremont Pass | 485:CO:SNTL |
| Summit County & Vail | Hoosier Pass | 531:CO:SNTL |
| Summit County & Vail | Grizzly Peak | 505:CO:SNTL |
| Summit County & Vail | Loveland Basin | 602:CO:SNTL |
| Summit County & Vail | Jackwhacker Gulch | 935:CO:SNTL |
| Summit County & Vail | Elliot Ridge | 1120:CO:SNTL |
| Summit County & Vail | Red Sandstone Rd, Vail Pass, Vail, Copper, Breckenridge, Keystone, Arapahoe Basin | forecast only |

Units are read from Open-Meteo's `daily_units`; with `precipitation_unit=inch` snowfall already comes back in inches.
