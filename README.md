# snow

Phone-first snow dashboard centered on Durango, CO: https://chiznitz.github.io/snow/

Static HTML/CSS/vanilla JS, no build step, no API keys. GitHub Pages serves `index.html` from the root of `main`.

Sites are defined in the `REGIONS` / `LOCATIONS` arrays in `index.html`. Each location gets one card with a snowpack panel (if it has a SNOTEL triplet) and a forecast panel, plus a row in the "At a glance" table.

- **Snowpack:** NRCS SNOTEL AWDB REST API, hourly SNWD/WTEQ.
- **Forecast:** Open-Meteo 16-day daily forecast, downscaled to each site's elevation, from six global models
  (ECMWF, GFS, ICON, GEM, UKMO, JMA) plus HRRR and NAM for the next 48 hours. Totals are the median of the models
  that cover the whole window; ranges are the lowest and highest model.
- **Chris Tomer:** `.github/workflows/tomer.yml` runs `scripts/tomer.py` each morning (14:15 and 15:15 UTC) and on
  manual dispatch. It reads his channel RSS, tries to fetch the newest video's transcript, and writes `tomer.json`.
  Optional repo secrets: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (AI summary instead of keyword extraction),
  `YT_PROXY_URL` (residential proxy) or `YT_COOKIES` (cookies.txt) if YouTube blocks the runner.
- **Snowfall map:** `.github/workflows/snowmap.yml` runs `scripts/snowmap.py` twice a day (11:40 and 23:40 UTC)
  and on manual dispatch. It samples Open-Meteo's hourly snowfall from the same six global models on a grid for
  each map area (West at 0.5°, San Juans and N. CO / WY at 0.15°, UT / ID at 0.25°) and writes 24h / 48h / 3d /
  7d / 14d totals to `snowmap.json`, plus totals at each location's own elevation for the yellow numbers. The
  page draws the field on a canvas over Esri World Imagery tiles with state lines from `borders.json`. A run is
  about 3,500 points, roughly a third of Open-Meteo's free 10k daily calls. When you add a location, add it to
  `POINTS` in the script too.
- **Biggest storm card:** the headline is the largest consensus storm across all spots, where a day only counts
  if at least two models have a forecast for it (`MIN_MODELS`); otherwise a lone GFS day 15–16 total becomes the
  "consensus". The "Why this storm?" panel shows the day-by-day model matrix, each model's terrain height at the
  spot (`terrain_m` in `snowmap.json`, fetched with `elevation=nan`), and the NWS/CPC discussion links.
- **NWS discussions:** `.github/workflows/afd.yml` runs `scripts/afd.py` every 6 hours. It pulls each office's
  Area Forecast Discussion from api.weather.gov (GJT, BOU, PUB, CYS, SLC, BOI), finds the long-range section, and
  writes a verbatim one-line excerpt to `afd.json`. Offices are mapped per region (`nws` in `REGIONS`, overridable
  per location).
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
