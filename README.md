# snow

Phone-first snow dashboard centered on Durango, CO: https://chiznitz.github.io/snow/

Static HTML/CSS/vanilla JS, no build step, no API keys. GitHub Pages serves `index.html` from the root of `main`.

Sites are defined in the `REGIONS` / `LOCATIONS` arrays in `index.html`. Each location gets one card with a snowpack panel (if it has a SNOTEL triplet) and a forecast panel, plus a row in the "At a glance" table.

- **Snowpack:** NRCS SNOTEL AWDB REST API, hourly SNWD/WTEQ.
- **Forecast:** Open-Meteo 16-day daily forecast, downscaled to each site's elevation.

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

Units are read from Open-Meteo's `daily_units`; with `precipitation_unit=inch` snowfall already comes back in inches.
