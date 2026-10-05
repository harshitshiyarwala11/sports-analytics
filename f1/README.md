# F1

Formula 1 data analysis using [FastF1](https://docs.fastf1.dev/), which provides
timing, lap, telemetry, weather and results data for sessions from 2018 onwards.

## Getting started

```python
import fastf1

# FastF1 downloads a lot of data, so always enable its cache.
# The cache folder is git-ignored.
fastf1.Cache.enable_cache("f1/cache")

session = fastf1.get_session(2024, "Monza", "R")
session.load()
laps = session.laps  # pandas DataFrame
```

Create the cache folder first (`mkdir -p f1/cache`) — FastF1 won't create it for you.

## Layout

- `cache/` — FastF1 cache (git-ignored)
- `data/` — any exported or downloaded data (git-ignored)
- Analysis scripts and notebooks live directly in this folder.
