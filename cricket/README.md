# Cricket

Cricket data analysis with pandas and matplotlib.

## Data sources

[Cricsheet](https://cricsheet.org/) publishes free ball-by-ball data for
international and major domestic matches in JSON and CSV formats. Downloads can be
fetched with `requests`:

```python
import requests
from pathlib import Path

Path("cricket/data").mkdir(parents=True, exist_ok=True)
url = "https://cricsheet.org/downloads/t20s_json.zip"
resp = requests.get(url, timeout=60)
resp.raise_for_status()
Path("cricket/data/t20s_json.zip").write_bytes(resp.content)
```

## Scripts

### `batting_stats.py` — a player's batting numbers, optionally at one ground

Reads Cricsheet JSON and prints matches, runs, balls, strike rate, average,
4s/6s, boundary %, dot ball %, phase splits (powerplay/middle/death) and every
innings. Names use Cricsheet's format (initials + surname, e.g. `DJ Mitchell`).

```bash
# T20Is (unzip t20s_json.zip into cricket/data/t20s first)
python cricket/batting_stats.py --player "DJ Mitchell" --team "New Zealand" \
    --data cricket/data/t20s --venue "Sky Stadium" "Westpac Stadium" \
    --out cricket/output/mitchell.xlsx
```

`--venue` matches part of the venue or city name and takes several names, so a
renamed ground (Westpac Stadium → Sky Stadium) can be covered in one run; use a
city (`--venue Wellington`) for every ground there.

`--out` writes an Excel workbook (`batting_excel.py`): Summary and By Phase sheets
built from formulas over the Innings and Balls sheets, so every number can be traced
back to the ball-by-ball data.

### `batter_splits.py` — one batter across splits, plus head-to-heads

Compares a batter in a host country, against one opponent (all venues) and over
their whole career, side by side, plus stats against named bowlers (runs, balls,
strike rate, dismissals, dot %, how out). Everything in the workbook is a formula
over the ball-by-ball "Balls" sheet.

```bash
# ODIs (unzip odis_json.zip into cricket/data/odis first)
python cricket/batter_splits.py --player "V Kohli" --team India --data cricket/data/odis \
    --host-label "New Zealand" --host-cities Auckland Hamilton "Mount Maunganui" Napier \
        Wellington Christchurch Dunedin Nelson Queenstown \
    --opponent "New Zealand" \
    --bowlers "MJ Henry" "MJ Santner" "LH Ferguson" \
    --out cricket/output/kohli_odi_nz.xlsx
```

Cricsheet doesn't store a match's country, so list the host country's cities.

## Layout

- `data/` — downloaded match data (git-ignored)
- `cache/` — any request caches (git-ignored)
- `output/` — files the scripts write (git-ignored)
- Analysis scripts and notebooks live directly in this folder.
