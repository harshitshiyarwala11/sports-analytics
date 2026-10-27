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
    --data cricket/data/t20s --venue Wellington --out cricket/output/mitchell.xlsx
```

`--venue` matches part of the venue or city, so renamed grounds (Westpac Stadium →
Sky Stadium) are both picked up.

## Layout

- `data/` — downloaded match data (git-ignored)
- `cache/` — any request caches (git-ignored)
- `output/` — files the scripts write (git-ignored)
- Analysis scripts and notebooks live directly in this folder.
