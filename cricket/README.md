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

## Layout

- `data/` — downloaded match data (git-ignored)
- `cache/` — any request caches (git-ignored)
- Analysis scripts and notebooks live directly in this folder.
