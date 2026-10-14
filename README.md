# snow

Phone-first snow dashboard for the San Juans around Durango, CO: https://chiznitz.github.io/snow/

Static HTML/CSS/vanilla JS, no build step, no API keys. GitHub Pages serves `index.html` from the root of `main`.

- **Snowpack:** NRCS SNOTEL AWDB REST API, hourly SNWD/WTEQ for Sharkstooth (1060:CO:SNTL) and Molas Lake (632:CO:SNTL).
- **Forecast:** Open-Meteo 16-day daily forecast, elevation-adjusted, for Sharkstooth, Molas Pass, Wolf Creek and Purgatory.

Units are read from Open-Meteo's `daily_units`; with `precipitation_unit=inch` snowfall already comes back in inches.
