# snow

Phone-first snow dashboard centered on Durango, CO: https://chiznitz.github.io/snow/

Static HTML/CSS/vanilla JS, no build step, no API keys. GitHub Pages serves `index.html` from the root of `main`.

Sites are defined in the `REGIONS` / `LOCATIONS` arrays in `index.html`. Each location gets one card with a snowpack panel (if it has a SNOTEL triplet) and a forecast panel, plus a row in the "At a glance" table.

- **Snowpack:** NRCS SNOTEL AWDB REST API, hourly SNWD/WTEQ.
- **Forecast:** Open-Meteo 16-day daily forecast, downscaled to each site's elevation, from six global models
  (ECMWF, GFS, ICON, GEM, UKMO, JMA) plus HRRR and NAM for the next 48 hours. Totals are the median of the models
  that cover the whole window; ranges are the lowest and highest model.
- **Loading and fallback:** `.github/workflows/live.yml` runs `scripts/live.py` every 2 hours and writes
  `live.json`, a snapshot of the exact SNOTEL (last 170 h), daily forecast, hourly forecast and 700 mb wind
  responses the page would fetch itself.
  The page renders from that snapshot first (same origin, ~25 KB gzipped), so it is readable before any
  third-party request is sent, then updates progressively: SNOTEL is always refreshed live; Open-Meteo is only
  called live when the snapshot is more than 2 hours old or you tap refresh. Every third-party request has an 8 s
  timeout and one retry, and a failure falls back to the newer of the last good response saved in the browser or
  the snapshot, with a yellow "Live data unavailable" note on the affected card. No single fetch can block the
  page, and non-critical build steps are wrapped so one failure can't blank it. When you add a location, add its
  SNOTEL triplet to `TRIPLETS` in `scripts/live.py` too.
- **Chris Tomer:** `.github/workflows/tomer.yml` runs `scripts/tomer.py` each morning (14:15 and 15:15 UTC) and on
  manual dispatch. It reads his channel RSS, tries to fetch the newest video's transcript, and writes `tomer.json`.
  Optional repo secrets: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (AI summary instead of keyword extraction),
  `YT_PROXY_URL` (residential proxy) or `YT_COOKIES` (cookies.txt) if YouTube blocks the runner.
- **Snowfall map:** `.github/workflows/snowmap.yml` runs `scripts/snowmap.py` twice a day (11:40 and 23:40 UTC)
  and on manual dispatch. It samples Open-Meteo's hourly snowfall from the same six global models on a grid for
  each map area (West at 0.5°, San Juans and N. CO / WY at 0.15°, UT / ID at 0.25°) and writes 24h / 48h / 3d /
  7d / 14d totals to `snowmap.json`, plus totals at each location's own elevation for the yellow numbers. The
  map opens on the San Juans view for first-time visitors (a saved choice wins). The
  page draws the field on a canvas over Esri World Imagery tiles with state lines from `borders.json`. A run is
  about 3,500 points, roughly a third of Open-Meteo's free 10k daily calls. When you add a location, add it to
  `POINTS` in the script too.
- **Snow forecast table:** one row per spot: Now (SNOTEL depth), Past (net depth change over the trailing 24h /
  48h / 72h / 7d from SNOTEL hourly, so settling means new snow is usually more than shown) and Next (forecast
  consensus for the next 24h / 48h / 72h / 7d / 14d, the same windows as the map). 24–72h are summed from the hour
  after now using one hourly Open-Meteo request for all 13 spots and the six global models (HRRR stored alongside);
  7d and 14d come from the daily forecast. A window only counts when at least two models cover it (`MIN_MODELS`),
  so a lone long-range model can't pose as the consensus. Zeros are blank dots; non-zero cells are colored pills
  with the model range underneath. Below 760px a Past / Next toggle picks which group shows beside the sticky
  location column; tap a header to sort. Tap a row to open that spot's card inline (one at a time); region rows
  collapse (San Juans open by default, remembered per device). `#loc-<id>` in the URL opens that card on load.
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
  (its streams block embedding), and Brundage serves its own JPGs. Purgatory's Verkada base stream is locked to
  purgatory.ski, so it is linked rather than embedded.

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

Units are read from Open-Meteo's `daily_units`; with `precipitation_unit=inch` snowfall already comes back in inches.
