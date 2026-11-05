"""Who runs past the pit window? Stint lengths vs the field, per compound, all season.

There is no official pit window in the data, so it is taken from what the field did.
For each race and compound, the "window" is the spread of tyre life (laps on the set
when it came off, so used sets count fairly) across completed green-flag stints: the
25th to 75th percentile. A stint "exceeds the window" when its tyre life is above the
75th percentile AND at least EXTRA_LAPS laps beyond the field's median.

Completed stint = the driver pitted and changed tyres afterwards. Left out: the final
stint (ran to the flag), stints ended by retirement, tyre changes under a red flag,
wet/intermediate tyres and 1-2 lap stints. Stops under a safety car or VSC count as
stints but are not used to set the window.

    python f1/pit_windows.py --year 2026
"""

import argparse

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from practice_race_pace import HERE, fetch  # noqa: E402
from track_dominance import BG, DRIVER_COLOURS, INK, INK_2, MUTED  # noqa: E402
from tyre_degradation import neutralised_laps  # noqa: E402

DRY = ["SOFT", "MEDIUM", "HARD"]
EXTRA_LAPS = 3
MIN_WINDOW_STINTS = 4
MAX_START_AGE = 20      # larger tyre ages at fitting are treated as data errors
GRIDLINE = "#2A3854"
plt.rcParams["font.family"] = "Liberation Sans"


def red_flag_laps(session_key):
    rc = pd.DataFrame(fetch("race_control", session_key=session_key))
    if rc.empty:
        return set()
    laps = rc[rc.message.str.contains("RED FLAG", na=False)].lap_number.dropna().astype(int)
    return {n + k for n in laps for k in (-1, 0, 1)}


def race_stints(session):
    key = session["session_key"]
    st = pd.DataFrame(fetch("stints", session_key=key))
    if st.empty:
        return pd.DataFrame()
    drivers = pd.DataFrame(fetch("drivers", session_key=key)).set_index("driver_number")
    red = red_flag_laps(key)
    neutral = neutralised_laps(key)
    st = st.dropna(subset=["lap_start", "lap_end"]).sort_values(["driver_number", "stint_number"])
    st["next_start"] = st.groupby("driver_number").lap_start.shift(-1)
    st["laps"] = st.lap_end - st.lap_start + 1
    # Used sets come from practice/qualifying (a few laps); larger starting ages are data
    # glitches (e.g. 59 "laps" on a set fitted on lap 59), so those count laps run only.
    age0 = st.tyre_age_at_start.fillna(0)
    st["tyre_life"] = age0.where(age0 <= MAX_START_AGE, 0) + st.laps
    st = st[st.next_start.notna()                     # pitted afterwards
            & st.compound.isin(DRY) & (st.laps >= 3)
            & ~st.lap_end.isin(red)].copy()           # not a red-flag tyre change
    st["under_sc"] = st.lap_end.isin(neutral)
    st["race"] = session["location"]
    st["date"] = session["date_start"][:10]
    st["driver"] = st.driver_number.map(drivers.name_acronym)
    st["team"] = st.driver_number.map(drivers.team_name)
    return st


def add_windows(st):
    rows = []
    for (race, comp), g in st.groupby(["race", "compound"]):
        ref = g[~g.under_sc].tyre_life
        if len(ref) < MIN_WINDOW_STINTS:
            continue
        q25, med, q75 = ref.quantile([0.25, 0.5, 0.75])
        g = g.assign(window_from=q25, window_median=med, window_to=q75)
        g["beyond_median"] = g.tyre_life - med
        g["exceeded"] = (g.tyre_life > q75) & (g.beyond_median >= EXTRA_LAPS)
        rows.append(g)
    return pd.concat(rows) if rows else pd.DataFrame()


def summary(st, compound=None):
    s = st if compound is None else st[st.compound == compound]
    g = s.groupby("driver")
    out = pd.DataFrame({
        "team": g.team.agg(lambda t: t.mode().iloc[0]),
        "stints": g.size(),
        "exceeded": g.exceeded.sum(),
        "races_exceeded": s[s.exceeded].groupby("driver").race.nunique(),
        "avg_laps_vs_median": g.beyond_median.mean(),
        "max_laps_vs_median": g.beyond_median.max(),
    }).fillna({"races_exceeded": 0})
    out["exceeded_pct"] = 100 * out.exceeded / out.stints
    return out.sort_values(["exceeded", "exceeded_pct", "avg_laps_vs_median"], ascending=False)


def draw(path, title, subtitle, table, highlight, notes, top_n=12):
    t = table[table.stints >= 3].head(top_n).iloc[::-1]
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
    fig.patch.set_facecolor(BG)
    fig.text(0.5, 0.955, title, ha="center", fontsize=36, color=INK, fontweight="bold")
    fig.text(0.5, 0.922, subtitle, ha="center", fontsize=19, color=INK_2)
    ax = fig.add_axes([0.24, 0.30, 0.56, 0.58])
    ax.set_facecolor(BG)
    colours = [DRIVER_COLOURS.get(d, "#5A6B8C") if d == highlight else "#5A6B8C"
               for d in t.index]
    ax.barh(t.index, t.exceeded, color=colours, height=0.62)
    for i, (d, r) in enumerate(t.iterrows()):
        ax.text(r.exceeded + 0.08, i, f"{int(r.exceeded)} of {int(r.stints)} stints  ·  "
                f"{r.avg_laps_vs_median:+.1f} laps vs median", va="center", fontsize=14,
                color=INK if d == highlight else INK_2,
                fontweight="bold" if d == highlight else "normal")
    ax.set_xlim(0, t.exceeded.max() * 1.9 + 0.5)
    ax.tick_params(axis="y", colors=INK, labelsize=16, length=0, pad=10)
    ax.tick_params(axis="x", colors=MUTED, labelsize=13)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.grid(axis="x", color=GRIDLINE, lw=0.8)
    ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("stints that ran past the field's pit window", color=MUTED, fontsize=14)
    for i, n in enumerate(notes):
        fig.text(0.07, 0.22 - 0.026 * i, n, fontsize=13.5, color=MUTED)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--driver", default="ANT", help="driver to detail and highlight")
    args = parser.parse_args()
    sessions = [s for s in fetch("sessions", year=args.year, session_name="Race")
                if pd.Timestamp(s["date_end"]) < pd.Timestamp.now(tz="UTC")]
    st = add_windows(pd.concat([race_stints(s) for s in sessions], ignore_index=True))
    pd.set_option("display.width", 220)
    print(f"{len(sessions)} races, {len(st)} completed dry stints with a window")
    soft = summary(st, "SOFT")
    print("\nSOFT tyres - most stints past the window:")
    print(soft.head(12).round(1).to_string())
    print("\nALL dry compounds:")
    print(summary(st).head(12).round(1).to_string())
    who = args.driver.upper()
    cols = ["date", "race", "compound", "lap_start", "lap_end", "tyre_life", "window_from",
            "window_median", "window_to", "beyond_median", "exceeded", "under_sc"]
    print(f"\n{who}: every completed stint")
    print(st[st.driver == who].sort_values("date")[cols].round(1).to_string(index=False))

    out = HERE / "output"
    out.mkdir(exist_ok=True)
    stem = f"{args.year}_pit_windows"
    with pd.ExcelWriter(out / f"{stem}.xlsx") as xl:
        soft.round(2).to_excel(xl, sheet_name="Soft by driver")
        summary(st).round(2).to_excel(xl, sheet_name="All dry by driver")
        st.sort_values(["date", "driver", "lap_start"])[["driver", "team"] + cols].round(1) \
            .to_excel(xl, sheet_name="Every stint", index=False)
    notes = [f"{len(sessions)} races of {args.year}. Window = middle half of the field's tyre life "
             "on that compound in that race",
             f"(25th-75th percentile of completed green-flag stints). Exceeded = above the "
             f"window and {EXTRA_LAPS}+ laps past the median.",
             "Tyre life counts laps on the set when it came off, so used sets count fairly.",
             "Left out: final stints, retirements, red-flag tyre changes, wet tyres. "
             "Data: OpenF1 stints."]
    path = out / f"{stem}_soft.png"
    draw(path, "LONG STINTS ON SOFTS", f"{args.year} season · who runs past the pit window",
         soft, who, notes)
    print("\nSaved", path)


if __name__ == "__main__":
    main()
