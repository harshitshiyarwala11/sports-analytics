"""Tyre degradation per stint from race lap times.

For every stint (one set of tyres), lap times are fuel-corrected (the car gets
lighter as fuel burns, so later laps are flattered) and a straight line is fitted
to corrected lap time against tyre age. The slope is the degradation: seconds lost
per lap of tyre age.

Laps left out: lap 1, pit in/out laps, laps under VSC / safety car / red flag (and
the lap the race restarts), and outliers more than OUTLIER_S slower than the line.
Only stints with at least MIN_LAPS clean laps are fitted.

    python f1/tyre_degradation.py --year 2026 --location "Mexico City" \
        --drivers VER HAM ANT LEC RUS NOR
"""

import argparse

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from practice_race_pace import HERE, fetch  # noqa: E402
from track_dominance import BG, DRIVER_COLOURS, FALLBACK, INK, INK_2, MUTED  # noqa: E402

FUEL_S_PER_LAP = 0.035   # assumed lap-time gain per lap of fuel burned
MIN_LAPS = 8
OUTLIER_S = 1.0
GRIDLINE = "#2A3854"
plt.rcParams["font.family"] = "Liberation Sans"


def neutralised_laps(session_key):
    """Laps run under VSC, safety car or red flag, plus each restart lap."""
    rc = pd.DataFrame(fetch("race_control", session_key=session_key)).sort_values("date")
    bad, start = set(), None
    for r in rc.itertuples():
        m, lap = r.message, r.lap_number
        if lap is None or pd.isna(lap):
            continue
        lap = int(lap)
        if "VSC DEPLOYED" in m or "SAFETY CAR DEPLOYED" in m or "RED FLAG" in m:
            start = lap if start is None else start
        elif start is not None and ("VSC ENDING" in m or "SAFETY CAR IN THIS LAP" in m
                                    or "STANDING START" in m or "SESSION STARTED" in m):
            bad.update(range(start, lap + 2))  # include the restart lap
            start = None
    return bad


def stint_laps(session_key):
    laps = pd.DataFrame(fetch("laps", session_key=session_key))
    stints = pd.DataFrame(fetch("stints", session_key=session_key))
    drivers = pd.DataFrame(fetch("drivers", session_key=session_key)).set_index("driver_number")
    total = int(laps.lap_number.max())
    bad = neutralised_laps(session_key)
    laps = laps.dropna(subset=["lap_duration"])
    out = laps.is_pit_out_lap.fillna(False).astype(bool)
    out_laps = set(zip(laps.driver_number[out], laps.lap_number[out]))
    keep = ((laps.lap_number > 1) & ~out & ~laps.lap_number.isin(bad)
            & np.array([(d, n + 1) not in out_laps
                        for d, n in zip(laps.driver_number, laps.lap_number)]))
    laps = laps[keep].merge(stints, on=["driver_number", "session_key", "meeting_key"])
    laps = laps[laps.lap_number.between(laps.lap_start, laps.lap_end)].copy()
    laps["tyre_age"] = laps.tyre_age_at_start + laps.lap_number - laps.lap_start
    laps["corrected"] = laps.lap_duration - FUEL_S_PER_LAP * (total - laps.lap_number)
    laps["driver"] = laps.driver_number.map(drivers.name_acronym)
    laps["team"] = laps.driver_number.map(drivers.team_name)
    return laps, total


def fit_stints(laps):
    rows, used = [], []
    for (drv, stint), g in laps.groupby(["driver", "stint_number"]):
        g = g.sort_values("lap_number")
        for _ in range(2):  # fit, drop outliers, refit
            if len(g) < MIN_LAPS:
                break
            slope, icpt = np.polyfit(g.tyre_age, g.corrected, 1)
            resid = g.corrected - (slope * g.tyre_age + icpt)
            g = g[resid < OUTLIER_S]
        if len(g) < MIN_LAPS:
            continue
        slope, icpt = np.polyfit(g.tyre_age, g.corrected, 1)
        rows.append({"driver": drv, "team": g.team.iloc[0], "stint": stint,
                     "compound": g.compound.iloc[0].title(),
                     "laps": f"{int(g.lap_start.iloc[0])}-{int(g.lap_end.iloc[0])}",
                     "clean_laps": len(g), "age_from": int(g.tyre_age.min()),
                     "age_to": int(g.tyre_age.max()), "deg_s_per_lap": slope,
                     "pace_s": g.corrected.median()})
        used.append(g.assign(fit=slope * g.tyre_age + icpt))
    return pd.DataFrame(rows), pd.concat(used)


def draw(path, title, subtitle, stints, used, drivers):
    colour = {d: DRIVER_COLOURS.get(d) for d in drivers}
    spare = iter(FALLBACK)
    colour = {d: c or next(spare) for d, c in colour.items()}
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
    fig.patch.set_facecolor(BG)
    fig.text(0.5, 0.955, title, ha="center", fontsize=38, color=INK, fontweight="bold")
    fig.text(0.5, 0.922, subtitle, ha="center", fontsize=19, color=INK_2)
    # One panel per race phase (each has at most one stint per driver). The restart
    # lap is the most common stint start in the second half of the race.
    first = int(used.lap_number.min())
    starts = stints.laps.str.split("-").str[0].astype(int)
    late = starts[starts > used.lap_number.max() / 2]
    restart = int(late.mode().min()) if not late.empty else None

    def phase(lap_start):
        if lap_start <= first + 1:
            return "Opening stint"
        if restart is not None and lap_start >= restart:
            return "After restart"
        return "Middle stint"

    stints = stints.assign(phase=[phase(int(l.split("-")[0])) for l in stints.laps])
    phases = [p for p in ("Opening stint", "Middle stint", "After restart")
              if p in set(stints.phase)]
    width = 0.86 / len(phases)
    lo = used.corrected.quantile(0.01) - 0.2
    hi = used.corrected.quantile(0.99) + 0.2
    for k, ph in enumerate(phases):
        ax = fig.add_axes([0.09 + k * width, 0.53, width - 0.05, 0.35])
        ax.set_facecolor(BG)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRIDLINE)
        ax.tick_params(colors=MUTED, labelsize=13)
        ax.grid(color=GRIDLINE, lw=0.8)
        ax.set_axisbelow(True)
        ax.set_ylim(lo, hi)
        sel = stints[stints.phase == ph]
        labels = []
        for r in sel.itertuples():
            g = used[(used.driver == r.driver) & (used.stint_number == r.stint)]
            c = colour[r.driver]
            ax.scatter(g.tyre_age, g.corrected, s=10, color=c, alpha=0.35, lw=0)
            ax.plot(g.tyre_age, g.fit, color=c, lw=2.5)
            labels.append((g.fit.iloc[-1], g.tyre_age.iloc[-1], f"{r.driver} {r.compound[0]}"))
        # Spread end labels so they don't overlap.
        gap = (hi - lo) * 0.045
        prev = None
        for y, x, txt in sorted(labels, reverse=True):
            y = y if prev is None else min(y, prev - gap)
            ax.text(x + 0.8, y, txt, color=INK, fontsize=11.5, va="center",
                    fontweight="bold", clip_on=False)
            prev = y
        ax.set_title(ph, color=INK_2, fontsize=17, loc="left")
        ax.set_xlabel("tyre age (laps)", color=MUTED, fontsize=12)
        if k:
            ax.set_yticklabels([])
        else:
            ax.set_ylabel("fuel-corrected lap time (s)", color=MUTED, fontsize=13)

    # Table: one row per stint, sorted by compound then degradation.
    tab = stints.sort_values(["compound", "deg_s_per_lap"],
                             key=lambda s: s.map({"Soft": 0, "Medium": 1, "Hard": 2})
                             if s.name == "compound" else s)
    heads = [("Driver", 0.07, "left"), ("Tyre", 0.25, "center"), ("Race laps", 0.37, "center"),
             ("Tyre age", 0.51, "center"), ("Deg / lap", 0.66, "center"),
             ("Over the stint", 0.83, "center")]
    top = 0.455
    for h, x, ha in heads:
        fig.text(x, top, h, fontsize=15, color=MUTED, fontweight="bold", ha=ha)
    step = min(0.032, 0.33 / max(len(tab), 1))
    for i, r in enumerate(tab.itertuples()):
        y = top - step * (i + 1)
        fig.patches.append(plt.Rectangle((0.07, y - 0.003), 0.010, 0.017,
                                         transform=fig.transFigure, color=colour[r.driver]))
        lost = r.deg_s_per_lap * (r.age_to - r.age_from)
        vals = [(f"{r.driver}", 0.09, "left", INK), (r.compound, 0.25, "center", INK_2),
                (r.laps, 0.37, "center", INK_2), (f"{r.age_from}-{r.age_to}", 0.51, "center", INK_2),
                (f"{r.deg_s_per_lap:+.3f}s", 0.66, "center", INK),
                (f"{lost:+.1f}s", 0.83, "center", INK_2)]
        for v, x, ha, col in vals:
            fig.text(x, y, v, fontsize=16, color=col, ha=ha,
                     fontweight="bold" if col == INK else "normal")
    notes = [f"Deg / lap = slope of fuel-corrected lap time vs tyre age (fuel effect assumed "
             f"{FUEL_S_PER_LAP:.3f}s per lap)",
             "Over the stint = time lost from first to last clean lap on that set   ·   "
             "S = Soft, M = Medium",
             "Excludes lap 1, pit laps, VSC/SC/red-flag laps and restarts; traffic still "
             "affects some laps",
             "Data: OpenF1 lap timing & stints"]
    for i, n in enumerate(notes):
        fig.text(0.07, 0.085 - 0.022 * i, n, fontsize=12.5, color=MUTED)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--drivers", nargs="+", default=[], help="driver codes for the graphic")
    args = parser.parse_args()
    key = {s["session_name"]: s["session_key"]
           for s in fetch("sessions", year=args.year, location=args.location)}["Race"]
    laps, total = stint_laps(key)
    stints, used = fit_stints(laps)
    pd.set_option("display.width", 200)
    print(f"Race laps: {total}. Neutralised laps excluded: {sorted(neutralised_laps(key))}")
    print("\nMedian degradation by compound (s/lap):")
    print(stints.groupby("compound").deg_s_per_lap.agg(["median", "count"]).round(3))
    print("\nAll fitted stints:")
    print(stints.sort_values(["compound", "deg_s_per_lap"]).round(3).to_string(index=False))
    out = HERE / "output"
    out.mkdir(exist_ok=True)
    stem = f"{args.year}_{args.location.replace(' ', '_').lower()}_tyre_deg"
    stints.round(3).to_excel(out / f"{stem}.xlsx", index=False)
    if args.drivers:
        sel = [d.upper() for d in args.drivers]
        path = out / f"{stem}.png"
        draw(path, "TYRE DEGRADATION · RACE",
             f"{args.location} GP {args.year} · {', '.join(sel)}",
             stints[stints.driver.isin(sel)], used[used.driver.isin(sel)], sel)
        print("Saved", path)


if __name__ == "__main__":
    main()
