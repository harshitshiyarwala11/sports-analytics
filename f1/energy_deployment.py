"""Estimate energy deployment patterns by power-unit maker from car telemetry.

Public telemetry has no hybrid-system channels (battery charge, MGU-K power), so this
looks at what deployment does to the speed trace on the longest full-throttle run,
the main straight, from Turn 17 exit to the Turn 1 braking point:

* time to accelerate 200 -> 330 km/h      (stronger deployment = quicker)
* acceleration in 200-250, 250-300 and 300-330 km/h bands (km/h per second)
* peak speed and how long the car holds it ("plateau", within 2 km/h of peak)
* speed lost at full throttle before braking ("clipping": deployment ending or
  harvesting while the driver is still flat out)

Qualifying uses each driver's fastest lap (maximum deployment). The race uses every
clean lap run in clean air (2+ s behind the car ahead, or leading) so slipstream
doesn't distort the straight. Results are medians per driver, then per maker.

    python f1/energy_deployment.py --year 2026 --location "Mexico City"
"""

import argparse
import json

import matplotlib
import numpy as np
import pandas as pd
import requests

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import straights_vs_corners as sc
from practice_race_pace import API, CACHE, HERE, fetch
from track_dominance import BG, INK, INK_2, MUTED, clean_laps, fetch_car_data_range

POWER_UNIT = {  # 2026 power-unit suppliers
    "Mercedes": "Mercedes", "McLaren": "Mercedes", "Williams": "Mercedes",
    "Alpine": "Mercedes", "Ferrari": "Ferrari", "Haas F1 Team": "Ferrari",
    "Cadillac": "Ferrari", "Red Bull Racing": "Red Bull Ford",
    "Racing Bulls": "Red Bull Ford", "Aston Martin": "Honda", "Audi": "Audi",
}
FULL = 95            # throttle % counted as flat out
BANDS = [(200, 250), (250, 300), (300, 330)]
CLEAN_AIR_S = 2.0
MIN_RACE_LAPS = 5    # clean-air laps a driver needs to count in the race
GRID = np.arange(-1250, 1, 10.0)  # metres before the end of full throttle


def on_grid(d, vv):
    """Speed resampled every 10 m along the straight (NaN where not covered)."""
    return np.interp(GRID, d, vv, left=np.nan, right=np.nan)


def straight(t, v, thr, brk, after):
    """The main-straight run ending at the first braking after time `after`.

    The run starts where the driver comes off the corner throttle (last sample below
    50% before the straight) and ends at the last full-throttle sample before braking,
    so brief mid-straight wobbles (gear shifts) don't split it. Returns (time, speed,
    distance-to-end, lift_coast_s) or None. lift_coast_s is the time between leaving
    full throttle and touching the brake (lift-and-coast, a common energy-saving move).
    """
    idx = np.flatnonzero((t > after) & (brk > 0) & (v > 250))
    if not len(idx):
        return None
    b = idx[0]
    full = np.flatnonzero(thr[:b] >= FULL)
    if not len(full):
        return None
    e = full[-1]
    low = np.flatnonzero(thr[:e] < 50)
    s = low[-1] + 1 if len(low) else 0
    if e - s < 15:
        return None
    tt, vv = t[s:e + 1], v[s:e + 1].astype(float)
    d = np.r_[0, np.cumsum((vv[1:] + vv[:-1]) / 2 / 3.6 * np.diff(tt))]
    return tt, vv, d - d[-1], t[b] - t[e]


def crossing(t, v, target):
    """Time at which speed first reaches `target` (linear interpolation)."""
    i = np.flatnonzero(v >= target)
    if not len(i) or i[0] == 0:
        return np.nan
    i = i[0]
    return t[i - 1] + (target - v[i - 1]) / (v[i] - v[i - 1]) * (t[i] - t[i - 1])


def metrics(tt, vv, d, lift_coast_s):
    peak_i = int(np.argmax(vv))
    peak = vv[peak_i]
    m = {
        "entry_kmh": vv[0],
        "t_200_330_s": crossing(tt, vv, 330) - crossing(tt, vv, 200),
        "peak_kmh": peak,
        "plateau_m": float(np.ptp(d[vv >= peak - 2])) if (vv >= peak - 2).sum() > 1 else 0.0,
        "clip_kmh": peak - vv[-1],
        "length_m": -d[0],
        "lift_coast_s": lift_coast_s,
    }
    for lo, hi in BANDS:
        m[f"accel_{lo}_{hi}"] = (hi - lo) / (crossing(tt, vv, hi) - crossing(tt, vv, lo))
    return m


def load_trace(car, t0):
    t = (pd.to_datetime(car.date, format="ISO8601") - t0).dt.total_seconds().to_numpy()
    o = np.argsort(t)
    return (t[o], car.speed.to_numpy()[o], car.throttle.to_numpy()[o],
            car.brake.to_numpy()[o])


def qualifying(session_key):
    rows = []
    for lap in sc.fastest_laps(session_key).itertuples():
        t0 = pd.Timestamp(lap.date_start)
        car = pd.DataFrame(fetch_car_data_range(
            session_key, lap.driver_number, t0 - pd.Timedelta(seconds=12),
            t0 + pd.Timedelta(seconds=lap.lap_duration * 0.3)))
        st = straight(*load_trace(car, t0), after=0) if not car.empty else None
        if st:
            rows.append({"driver": lap.name_acronym, "team": lap.team_name,
                         "laps": 1, **metrics(*st), "trace": on_grid(st[2], st[1])})
    return pd.DataFrame(rows)


def fetch_intervals(session_key):
    path = CACHE / f"intervals_session_key-{session_key}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = requests.get(f"{API}/intervals?session_key={session_key}", timeout=300).json()
    path.write_text(json.dumps(data))
    return data


def race(session_key):
    laps = clean_laps(session_key)
    drivers = pd.DataFrame(fetch("drivers", session_key=session_key)).set_index("driver_number")
    iv = pd.DataFrame(fetch_intervals(session_key))
    iv["t"] = pd.to_datetime(iv.date, format="ISO8601")
    iv["gap"] = pd.to_numeric(iv.interval, errors="coerce")
    rows = []
    for n, dl in laps.groupby("driver_number"):
        starts = pd.to_datetime(dl.date_start, format="ISO8601")
        pad = pd.Timedelta(seconds=5)
        car = pd.DataFrame(fetch_car_data_range(
            session_key, n, starts.min() - pad,
            (starts + pd.to_timedelta(dl.lap_duration, unit="s")).max() + pad))
        if car.empty:
            continue
        t_ref = starts.min()
        t, v, thr, brk = load_trace(car, t_ref)
        gaps = iv[iv.driver_number == n].sort_values("t")
        per = []
        for s in starts:
            g = gaps[gaps.t <= s].gap
            # interval 0 = leading; NaN (lapped / no data) is skipped
            if g.empty or pd.isna(g.iloc[-1]) or (0 < g.iloc[-1] < CLEAN_AIR_S):
                continue
            st = straight(t, v, thr, brk, after=(s - t_ref).total_seconds())
            if st and -st[2][0] > 900:  # a full main straight, not a part-throttle exit
                per.append((metrics(*st), on_grid(st[2], st[1])))
        if len(per) >= MIN_RACE_LAPS:
            r = drivers.loc[n]
            rows.append({"driver": r.name_acronym, "team": r.team_name, "laps": len(per),
                         **pd.DataFrame([m for m, _ in per]).median().to_dict(),
                         "trace": np.nanmedian([tr for _, tr in per], axis=0)})
    return pd.DataFrame(rows)


def by_maker(df):
    df = df.assign(maker=df.team.map(POWER_UNIT))
    cols = ["entry_kmh", "t_200_330_s", "accel_200_250", "accel_250_300", "accel_300_330",
            "peak_kmh", "plateau_m", "clip_kmh", "lift_coast_s"]
    agg = df.groupby("maker")[cols].median()  # median: one odd lap can't swing a maker
    agg.insert(0, "drivers", df.groupby("maker").driver.count())
    traces = {m: np.nanmedian(np.vstack(g.trace.to_list()), axis=0)
              for m, g in df.groupby("maker")}
    return agg.sort_values("t_200_330_s"), df, traces


# Dark-mode categorical palette, fixed order per maker (validated adjacent pairs).
MAKER_COLOURS = {"Mercedes": "#3987e5", "Ferrari": "#d95926", "Red Bull Ford": "#199e70",
                 "Honda": "#c98500", "Audi": "#d55181"}
GRIDLINE = "#2A3854"
plt.rcParams["font.family"] = "Liberation Sans"


def _style(ax):
    ax.set_facecolor(BG)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRIDLINE)
    ax.tick_params(colors=MUTED, labelsize=14)
    ax.grid(color=GRIDLINE, lw=0.8)
    ax.set_axisbelow(True)


def draw(path, title, subtitle, makers, traces, note):
    """Speed along the main straight per maker (full + top-end zoom) and a metric table."""
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
    fig.patch.set_facecolor(BG)
    fig.text(0.5, 0.955, title, ha="center", fontsize=36, color=INK, fontweight="bold")
    fig.text(0.5, 0.922, subtitle, ha="center", fontsize=19, color=INK_2)
    order = [m for m in MAKER_COLOURS if m in traces]

    ax = fig.add_axes([0.10, 0.62, 0.36, 0.26])
    zoom = fig.add_axes([0.55, 0.62, 0.30, 0.26])
    for a in (ax, zoom):
        _style(a)
    for m in order:
        ax.plot(GRID, traces[m], color=MAKER_COLOURS[m], lw=2)
        zoom.plot(GRID, traces[m], color=MAKER_COLOURS[m], lw=2)
    ax.set_xlim(-1250, 0)
    ax.set_ylim(100, 360)
    zoom.set_xlim(-600, 0)
    lo = np.nanmin([np.nanmin(traces[m][GRID >= -600]) for m in order])
    zoom.set_ylim(max(lo - 4, 300), 354)
    ax.set_title("Whole straight", color=INK_2, fontsize=17, loc="left")
    zoom.set_title("Last 600 m: top speed & clipping", color=INK_2, fontsize=17, loc="left")
    for a in (ax, zoom):
        a.set_xlabel("metres before lifting for Turn 1", color=MUTED, fontsize=13)
    ax.set_ylabel("km/h", color=MUTED, fontsize=13)
    # Direct labels at the end of the zoomed lines, spread so they don't overlap.
    ends = sorted(((traces[m][-1], m) for m in order), reverse=True)
    y_prev = None
    for y, m in ends:
        y_lab = y if y_prev is None else min(y, y_prev - 2.6)
        zoom.text(8, y_lab, m, color=INK, fontsize=13, va="center", clip_on=False)
        y_prev = y_lab
    # Legend (identity is never colour alone: lines are also labelled).
    fig.legend([plt.Line2D([], [], color=MAKER_COLOURS[m], lw=4) for m in order], order,
               loc="upper center", bbox_to_anchor=(0.5, 0.585), ncol=len(order),
               frameon=False, fontsize=15, labelcolor=INK)

    # Metric table.
    cols = [("Power unit", None), ("Drivers", "drivers"), ("200→330\nkm/h", "t_200_330_s"),
            ("Accel\n300→330", "accel_300_330"), ("Peak\nkm/h", "peak_kmh"),
            ("Lost before\nbraking", "clip_kmh"), ("Lift &\ncoast", "lift_coast_s")]
    xs = [0.07, 0.31, 0.43, 0.56, 0.67, 0.78, 0.91]
    top = 0.50
    for (h, _), x in zip(cols, xs):
        fig.text(x, top, h, fontsize=14, color=MUTED, fontweight="bold", va="center",
                 ha="left" if x == xs[0] else "center", linespacing=1.2)
    fmt = {"drivers": "{:.0f}", "t_200_330_s": "{:.2f}s", "accel_300_330": "{:.1f}",
           "peak_kmh": "{:.0f}", "clip_kmh": "{:.0f} km/h", "lift_coast_s": "{:.2f}s"}
    for i, (m, r) in enumerate(makers.iterrows()):
        y = top - 0.055 * (i + 1)
        fig.patches.append(plt.Rectangle((0.07, y - 0.004), 0.012, 0.022,
                                         transform=fig.transFigure, color=MAKER_COLOURS[m]))
        fig.text(0.09, y, m, fontsize=17, color=INK, fontweight="bold")
        for (h, c), x in zip(cols[1:], xs[1:]):
            fig.text(x, y, fmt[c].format(r[c]), fontsize=17, color=INK_2, ha="center")
    fig.text(0.07, 0.16, "200→330 km/h: time to accelerate (lower = stronger deployment)   ·   "
             "Accel: km/h per second", fontsize=13, color=MUTED)
    fig.text(0.07, 0.135, "Lost before braking: speed lost while still flat out "
             "(deployment fading / harvesting)", fontsize=13, color=MUTED)
    fig.text(0.07, 0.11, "Lift & coast: time off throttle before braking   ·   "
             "medians per driver, then per power unit", fontsize=13, color=MUTED)
    fig.text(0.07, 0.07, note, fontsize=13, color=MUTED)
    fig.text(0.07, 0.045, "Estimated from speed/throttle telemetry (OpenF1); no hybrid-system "
             "data is public. Car drag also affects these numbers.", fontsize=13, color=MUTED)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--location", required=True)
    args = parser.parse_args()
    keys = {s["session_name"]: s["session_key"]
            for s in fetch("sessions", year=args.year, location=args.location)}
    pd.set_option("display.width", 220)
    out = HERE / "output"
    out.mkdir(exist_ok=True)
    stem = f"{args.year}_{args.location.replace(' ', '_').lower()}_energy"
    results = {}
    for name, fn in (("Qualifying", qualifying), ("Race", race)):
        drivers = fn(keys[name])
        makers, drivers, traces = by_maker(drivers)
        results[name] = (makers, drivers, traces)
        print(f"\n=== {name}: by power unit")
        print(makers.round(2).to_string())
        print(f"\n--- {name}: by driver")
        print(drivers.drop(columns="trace").sort_values(["maker", "t_200_330_s"])
              .round(2).to_string(index=False))
    notes = {"Qualifying": "Qualifying: each driver's fastest lap (maximum deployment).",
             "Race": f"Race: clean laps 2+ s behind the car ahead (or leading); "
                     f"drivers with {MIN_RACE_LAPS}+ such laps."}
    for name, (makers, _, traces) in results.items():
        path = out / f"{stem}_{name.lower()}.png"
        draw(path, "ENERGY DEPLOYMENT · MAIN STRAIGHT",
             f"{args.location} GP {args.year} · {name} · by power unit", makers, traces,
             notes[name])
        print("Saved", path)
    with pd.ExcelWriter(out / f"{stem}.xlsx") as xl:
        for name, (makers, drivers, _) in results.items():
            makers.round(2).to_excel(xl, sheet_name=f"{name} by maker")
            drivers.drop(columns="trace").round(2).to_excel(
                xl, sheet_name=f"{name} by driver", index=False)
    return results


if __name__ == "__main__":
    main()
