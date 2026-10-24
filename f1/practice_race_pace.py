"""Sector-by-sector race pace (long runs) from F1 practice sessions.

Data comes from the OpenF1 API (https://openf1.org), which needs no login.
Responses are cached in f1/data/openf1/ (git-ignored).

Usage:
    python f1/practice_race_pace.py --year 2026 --location Austin
    python f1/practice_race_pace.py --year 2026 --location Austin --sessions "Practice 2"
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import requests
from matplotlib.colors import LinearSegmentedColormap

API = "https://api.openf1.org/v1"
HERE = Path(__file__).resolve().parent
CACHE = HERE / "data" / "openf1"

# A lap is a push lap if it is within this factor of the session's fastest lap
# (drops cool-down laps, which are typically 10-20% slower).
PUSH_LAP_FACTOR = 1.10
# A long run is at least this many consecutive push laps on one set of tyres.
MIN_RUN_LAPS = 5
# Inside a run, laps further than this from the run median are dropped
# (traffic, mistakes, a one-off qualifying lap).
RUN_OUTLIER_FACTOR = 0.02

SECTORS = ["duration_sector_1", "duration_sector_2", "duration_sector_3"]


def fetch(endpoint, refresh=False, **params):
    """GET an OpenF1 endpoint, caching the JSON response on disk."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = "_".join([endpoint] + [f"{k}-{v}" for k, v in sorted(params.items())])
    path = CACHE / f"{key.replace(' ', '')}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    resp = requests.get(f"{API}/{endpoint}", params=params, timeout=60)
    if resp.status_code == 404:  # OpenF1 answers 404 when there is no data yet
        return []
    resp.raise_for_status()
    data = resp.json()
    path.write_text(json.dumps(data))
    return data


def long_run_laps(session_key, refresh=False):
    """Return clean long-run laps for one session, with driver and tyre info."""
    laps = pd.DataFrame(fetch("laps", refresh, session_key=session_key))
    stints = pd.DataFrame(fetch("stints", refresh, session_key=session_key))
    drivers = pd.DataFrame(fetch("drivers", refresh, session_key=session_key))
    if laps.empty or stints.empty:
        return pd.DataFrame()

    # Attach the stint (compound, tyre age) each lap belongs to.
    laps = laps.merge(stints, on="driver_number", suffixes=("", "_stint"))
    laps = laps[laps.lap_number.between(laps.lap_start, laps.lap_end)]

    clean = laps[
        ~laps.is_pit_out_lap.fillna(False).astype(bool)
        & (laps.lap_number < laps.lap_end)  # last lap of a stint is the in-lap
        & laps[["lap_duration"] + SECTORS].notna().all(axis=1)
    ].copy()

    clean = clean[clean.lap_duration <= clean.lap_duration.min() * PUSH_LAP_FACTOR]

    # Split each stint into blocks of consecutive push laps; a block is one run.
    clean = clean.sort_values(["driver_number", "lap_number"])
    new_block = (clean.lap_number.diff() != 1) | (clean.driver_number.diff() != 0)
    clean["run_id"] = new_block.cumsum()
    run_len = clean.groupby("run_id").lap_number.transform("size")
    clean = clean[run_len >= MIN_RUN_LAPS]

    run_median = clean.groupby("run_id").lap_duration.transform("median")
    clean = clean[(clean.lap_duration / run_median - 1).abs() <= RUN_OUTLIER_FACTOR]
    clean = clean[clean.groupby("run_id").lap_number.transform("size") >= MIN_RUN_LAPS]
    clean["tyre_age"] = clean.tyre_age_at_start + clean.lap_number - clean.lap_start

    clean = clean.merge(
        drivers[["driver_number", "name_acronym", "team_name"]], on="driver_number"
    )
    return clean


def summarise(laps):
    """One row per driver: their longest long run, averaged sector by sector."""
    runs = (
        laps.groupby(["name_acronym", "team_name", "run_id", "compound"])
        .agg(
            laps=("lap_number", "size"),
            tyre_age_start=("tyre_age", "min"),
            s1=("duration_sector_1", "mean"),
            s2=("duration_sector_2", "mean"),
            s3=("duration_sector_3", "mean"),
            lap=("lap_duration", "mean"),
        )
        .reset_index()
    )
    best = runs.sort_values(["laps", "lap"], ascending=[False, True])
    best = best.drop_duplicates("name_acronym").sort_values("lap").reset_index(drop=True)
    for col in ["s1", "s2", "s3", "lap"]:
        best[f"{col}_gap"] = best[col] - best[col].min()
    return best


def plot(summary, title, path):
    """Heatmap of time lost to the best long run in each sector."""
    cols = ["s1_gap", "s2_gap", "s3_gap", "lap_gap"]
    values = summary[cols].to_numpy()
    cmap = LinearSegmentedColormap.from_list(
        "blues", ["#f4f8fd", "#9ec5f4", "#3987e5", "#1c5cab", "#0d366b"]
    )

    fig, ax = plt.subplots(figsize=(8, 0.42 * len(summary) + 1.8))
    vmax = max(values.max(), 0.1)
    ax.imshow(values, cmap=cmap, aspect="auto", vmin=0, vmax=vmax)
    for i, row in summary.iterrows():
        for j, col in enumerate(cols):
            v = row[col]
            ax.text(
                j, i, "best" if v == 0 else f"+{v:.3f}",
                ha="center", va="center", fontsize=8.5,
                color="white" if v > vmax * 0.55 else "#1f1f1f",
            )

    labels = [
        f"{r.name_acronym}  {r.compound[0]}·{r.laps}L" for r in summary.itertuples()
    ]
    ax.set_yticks(range(len(summary)), labels, fontsize=9)
    ax.set_xticks(range(4), ["Sector 1", "Sector 2", "Sector 3", "Lap"], fontsize=9)
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, loc="left", fontsize=11, pad=28)
    fig.text(
        0.01, 0.005,
        "Seconds lost to the best long-run average in each column. "
        "Label: driver, compound (S/M/H), laps in run. Data: OpenF1.",
        fontsize=7.5, color="#555555",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--location", required=True, help='e.g. "Austin", "Monza"')
    parser.add_argument(
        "--sessions", nargs="+", default=["Practice 1", "Practice 2", "Practice 3"]
    )
    parser.add_argument("--out", type=Path, default=HERE / "output")
    parser.add_argument("--refresh", action="store_true", help="ignore cached data")
    args = parser.parse_args()

    sessions = fetch("sessions", args.refresh, year=args.year, location=args.location)
    args.out.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 200)

    for s in sessions:
        name = s["session_name"]
        if name not in args.sessions:
            continue
        laps = long_run_laps(s["session_key"], args.refresh)
        if laps.empty:
            print(f"\n{name}: no long-run data (session may not have run yet)\n")
            continue
        summary = summarise(laps)
        slug = f"{args.year}_{args.location}_{name}".replace(" ", "_").lower()
        summary.to_csv(args.out / f"{slug}_race_pace.csv", index=False)
        plot(
            summary,
            f"{args.year} {args.location} — {name}: long-run pace by sector",
            args.out / f"{slug}_race_pace.png",
        )
        print(f"\n{name} — average of each driver's longest long run")
        print(
            summary[["name_acronym", "team_name", "compound", "laps", "tyre_age_start",
                     "s1", "s2", "s3", "lap", "lap_gap"]]
            .round(3)
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
