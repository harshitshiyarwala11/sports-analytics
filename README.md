# sports-analytics

Exploring Formula 1 and cricket data with Python.

## Structure

| Folder | What's in it |
|--------|--------------|
| [`f1/`](f1/) | Formula 1 analysis — lap times, telemetry, race results via FastF1 |
| [`cricket/`](cricket/) | Cricket analysis — ball-by-ball and match data (e.g. from Cricsheet) |

Each folder has its own README with data sources and getting-started notes.

## Setup

Requires Python 3.9+.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Dependencies:

- **pandas** — data wrangling
- **matplotlib** — plotting
- **fastf1** — F1 timing and telemetry data
- **requests** — downloading datasets

## Data

Downloaded data and cache folders (`data/`, `cache/`, etc.) are git-ignored, so
datasets stay local and only code is committed. Re-run the download steps in each
folder's README to fetch data on a new machine.
