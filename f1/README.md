# F1

Formula 1 data analysis using [FastF1](https://docs.fastf1.dev/) and the
[OpenF1](https://openf1.org) API.

## Scripts

### `practice_race_pace.py` — long-run pace by sector

Finds each driver's longest race-pace run in practice (at least 5 consecutive push
laps on one set of tyres) and averages sector 1, 2, 3 and lap times. Uses OpenF1,
so no login is needed.

```bash
python f1/practice_race_pace.py --year 2026 --location Austin
python f1/practice_race_pace.py --year 2026 --location Austin --sessions "Practice 2" --refresh
```

Writes a CSV and a heatmap per session to `f1/output/` and prints the table.
Use `--refresh` to re-download data for a session that was still in progress.

### `practice_laps_to_excel.py` — every lap to Excel

Builds a workbook with two sheets: **All Laps** (every lap with sector 1/2/3 and
lap times, average speed for each, tyre and lap type) and **Averages** (each
driver's average per session over representative laps). Speeds and averages are
Excel formulas. Sector lengths are estimated from speed telemetry and scaled to
the official lap length you pass in.

```bash
python f1/practice_laps_to_excel.py --year 2026 --location Austin --lap-km 5.513
```

## FastF1 quick start

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

The official F1 timing feed now requires an F1 account. If loading fails with
authentication warnings, set the `F1_USERNAME` and `F1_PASSWORD` environment
variables, or use OpenF1 instead (as `practice_race_pace.py` does).

## Layout

- `cache/` — FastF1 cache (git-ignored)
- `output/` — charts and CSVs produced by the scripts (git-ignored)
- `data/` — downloaded data, including the OpenF1 cache (git-ignored)
- Analysis scripts and notebooks live directly in this folder.
