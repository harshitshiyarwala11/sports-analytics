"""Track-dominance map: the fastest driver on each straight and corner section.

Uses straights_vs_corners.py to split the lap into full-throttle straights and
corner sections (from the session's fastest lap), times every driver's fastest
valid lap through each section, and colours the circuit by the section winner.
The circuit outline comes from a hand-traced map in circuits.py when one exists,
otherwise from the reference lap's car position data (OpenF1).

    python f1/track_dominance.py --year 2026 --location "Mexico City" --lap-km 4.304 \
        --sections "Main straight" "Turns 1-3" "Back straight" "Turns 4-6" \
                   "Straight to T7" "Esses (T7-11)" "Straight to T12" "Stadium (T12-17)"

Section names are optional labels in lap order; the main straight is split by the
finish line, so its two parts are merged into the first section.
"""

import argparse
import hashlib
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

import straights_vs_corners as sc  # noqa: E402
from circuits import CIRCUITS, label_positions, traced_outline  # noqa: E402
from practice_race_pace import API, CACHE, HERE, fetch  # noqa: E402

# Dark-mode categorical palette, fixed order (validated for colour-vision deficiency).
PALETTE = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9",
           "#e66767"]
# Fixed colours for regular front-runners, so a driver looks the same on every graphic.
# Chosen on the dark background for the widest separation between the two reds and
# the two greens; every section also carries a driver label, so colour is never the
# only cue. Other drivers get FALLBACK colours in order.
DRIVER_COLOURS = {
    "HAM": "#E8302F",  # scarlet
    "LEC": "#B5175F",  # crimson
    "VER": "#2F7FDB",  # blue
    "NOR": "#F28C1A",  # orange
    "ANT": "#3DAF2C",  # green
    "RUS": "#12B5A5",  # turquoise green
}
FALLBACK = ["#9085e9", "#c98500", "#8a97ad", "#d55181"]
BG, INK, INK_2, MUTED, TRACK = "#0B1426", "#FFFFFF", "#C9D3E3", "#8A97AD", "#2A3854"
plt.rcParams["font.family"] = "Liberation Sans"


def fetch_location(session_key, driver_number, start, end):
    """Car x/y position between two timestamps, cached."""
    query = (f"session_key={session_key}&driver_number={driver_number}"
             f"&date>={start.isoformat()}&date<={end.isoformat()}")
    path = CACHE / f"location_{hashlib.md5(query.encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text())
    resp = requests.get(f"{API}/location?{query}", timeout=60)
    data = resp.json()
    if not resp.ok or not isinstance(data, list):
        raise SystemExit(f"OpenF1 location data unavailable: {data}")
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def section_times(session_key, lap_km, window=None):
    """Per-driver time through each section (main straight parts merged)."""
    best = sc.fastest_laps(session_key, window)
    ref = best.iloc[0]
    zones = sc.zones(sc.trace(session_key, ref), lap_km * 1000)
    times = {}
    for lap in best.itertuples():
        tr = sc.trace(session_key, lap)
        dt = np.diff(np.interp(np.r_[zones.start.to_numpy(), 1.0], tr.frac, tr.t))
        times[(lap.full_name.title(), lap.name_acronym, lap.team_name)] = dt
    table = pd.DataFrame(times).T
    table.index.names = ["Driver", "Code", "Team"]
    # The lap starts and ends on the main straight: merge its two parts.
    if zones.straight.iloc[0] and zones.straight.iloc[-1] and len(zones) > 2:
        last = table.columns[-1]
        table[table.columns[0]] = table[table.columns[0]] + table[last]
        table = table.drop(columns=last)
        zones = zones.iloc[:-1].copy()
    return table, zones, ref


def fetch_car_data_range(session_key, driver_number, start, end):
    """Car telemetry for a long window (e.g. a whole race), cached."""
    query = (f"session_key={session_key}&driver_number={driver_number}"
             f"&date>={start.isoformat()}&date<={end.isoformat()}")
    path = CACHE / f"car_data_{hashlib.md5(query.encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text())
    resp = requests.get(f"{API}/car_data?{query}", timeout=300)
    data = resp.json()
    if not resp.ok or not isinstance(data, list):
        raise SystemExit(f"OpenF1 car data unavailable: {data}")
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def clean_laps(session_key, window=None, slow_factor=1.07):
    """Representative laps: no lap 1, out-laps, in-laps, deleted laps, or laps more
    than slow_factor slower than the driver's own best (safety car, traffic)."""
    laps = pd.DataFrame(fetch("laps", session_key=session_key))
    bad = sc.deleted_laps(session_key, laps)
    laps = laps.dropna(subset=["lap_duration", "date_start"]).copy()
    if window:
        started = pd.to_datetime(laps.date_start, format="ISO8601")
        laps = laps[(started >= window[0]) & (started <= window[1])]
    out = laps.is_pit_out_lap.fillna(False).astype(bool)
    out_laps = set(zip(laps.driver_number[out], laps.lap_number[out]))
    keep = (
        (laps.lap_number > 1) & ~out
        & np.array([(d, n + 1) not in out_laps
                    for d, n in zip(laps.driver_number, laps.lap_number)])
        & np.array([(d, n) not in bad for d, n in zip(laps.driver_number, laps.lap_number)])
    )
    laps = laps[keep]
    best = laps.groupby("driver_number").lap_duration.transform("min")
    return laps[laps.lap_duration <= best * slow_factor]


def average_section_speeds(session_key, lap_km, window=None, min_laps=10):
    """Average speed (km/h) through each section over every clean lap.

    Sections come from the session's fastest lap, as in section_times(). Rows are
    ordered by average lap time; also returns the number of laps averaged per driver.
    Drivers with fewer than min_laps clean laps (e.g. early retirements) are left out.
    """
    best = sc.fastest_laps(session_key, window)
    ref = best.iloc[0]
    zones = sc.zones(sc.trace(session_key, ref), lap_km * 1000)
    laps = clean_laps(session_key, window)
    drivers = pd.DataFrame(fetch("drivers", session_key=session_key)).set_index("driver_number")
    rows, counts, avg_lap = {}, {}, {}
    bounds = np.r_[zones.start.to_numpy(), 1.0]
    for n, dl in laps.groupby("driver_number"):
        starts = pd.to_datetime(dl.date_start, format="ISO8601")
        pad = pd.Timedelta(seconds=5)
        car = pd.DataFrame(fetch_car_data_range(
            session_key, n, starts.min() - pad,
            (starts + pd.to_timedelta(dl.lap_duration, unit="s")).max() + pad))
        if car.empty:
            continue
        t_all = pd.to_datetime(car.date, format="ISO8601").astype("int64").to_numpy() / 1e9
        order = np.argsort(t_all)
        t_all, v_all = t_all[order], car.speed.to_numpy()[order] / 3.6
        d_all = np.concatenate([[0], np.cumsum((v_all[1:] + v_all[:-1]) / 2 * np.diff(t_all))])
        per_lap = []
        for t0, dur in zip(starts.astype("int64").to_numpy() / 1e9, dl.lap_duration):
            d0, d1 = np.interp([t0, t0 + dur], t_all, d_all)
            if d1 - d0 < 0.9 * lap_km * 1000:  # telemetry gap: skip the lap
                continue
            # Time at which the car reaches each section boundary (fraction of lap).
            per_lap.append(np.diff(np.interp(d0 + bounds * (d1 - d0), d_all, t_all)))
        if len(per_lap) < min_laps:
            continue
        r = drivers.loc[n]
        key = (r.full_name.title(), r.name_acronym, r.team_name or "")
        rows[key] = np.mean(per_lap, axis=0)
        counts[key] = len(per_lap)
        avg_lap[key] = dl.lap_duration.mean()
    times = pd.DataFrame(rows).T
    times.index.names = ["Driver", "Code", "Team"]
    times = times.loc[sorted(times.index, key=lambda k: avg_lap[tuple(k)])]
    if zones.straight.iloc[0] and zones.straight.iloc[-1] and len(zones) > 2:
        last = times.columns[-1]
        times[times.columns[0]] = times[times.columns[0]] + times[last]
        times = times.drop(columns=last)
        length = zones.length_m.to_numpy()
        length = np.r_[length[0] + length[-1], length[1:-1]]
        zones = zones.iloc[:-1].copy()
        zones["length_m"] = length
    speeds = times.rdiv(zones.length_m.to_numpy(), axis=1) * 3.6
    return speeds, zones, ref, counts


def outline(session_key, ref):
    """Reference lap's x/y positions with each point's fraction of lap distance."""
    t0 = pd.Timestamp(ref.date_start)
    end = t0 + pd.Timedelta(seconds=ref.lap_duration)
    loc = pd.DataFrame(fetch_location(session_key, ref.driver_number,
                                      t0 - pd.Timedelta(seconds=1), end + pd.Timedelta(seconds=1)))
    t = (pd.to_datetime(loc.date, format="ISO8601") - t0).dt.total_seconds().to_numpy()
    keep = (t >= 0) & (t <= ref.lap_duration)
    tr = sc.trace(session_key, ref)
    frac = np.interp(t[keep], tr.t, tr.frac)
    xy = np.column_stack([loc.x.to_numpy()[keep], loc.y.to_numpy()[keep]]).astype(float)
    return frac, xy


def colours_for(tables, higher_is_better=False):
    """One fixed colour per section winner across several maps, in lap-time order.

    Rows of each table are in lap-time order, so a driver keeps the same colour on
    every map drawn with the result.
    """
    winners = {w[0] for t in tables
               for w in (t.idxmax() if higher_is_better else t.idxmin())}
    return colour_map(tables, winners)


def colour_map(tables, winners):
    """Driver name -> colour: DRIVER_COLOURS by code, else FALLBACK in lap-time order."""
    code_of = {i[0]: i[1] for t in tables for i in t.index}
    order = [d for d in dict.fromkeys(i[0] for t in tables for i in t.index) if d in winners]
    spare = iter(FALLBACK)
    colours = {}
    for d in order:
        colours[d] = DRIVER_COLOURS.get(code_of[d]) or next(spare, None)
        if colours[d] is None:
            raise SystemExit("More section winners than colours.")
    return colours


def draw(path, title, subtitle, table, zones, frac, xy, names, label_at=None, colour=None,
         speed=False, notes=None):
    """speed=False: table holds times (lowest wins); speed=True: km/h (highest wins)."""
    winners = table.idxmax() if speed else table.idxmin()
    colour = colour or colours_for([table], speed)

    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
    fig.patch.set_facecolor(BG)
    fig.text(0.5, 0.955, title, ha="center", fontsize=40, color=INK, fontweight="bold")
    fig.text(0.5, 0.92, subtitle, ha="center", color=INK_2,
             fontsize=21 if len(subtitle) <= 64 else 21 * 64 / len(subtitle))

    ax = fig.add_axes([0.06, 0.39, 0.88, 0.50])
    ax.set_facecolor(BG)
    ax.set_aspect("equal")
    ax.axis("off")
    pts = np.vstack([xy, xy[:1]])
    fr = np.r_[frac, 1.0]
    ax.plot(pts[:, 0], pts[:, 1], color=TRACK, lw=22, solid_capstyle="round", zorder=1)
    segs = np.stack([pts[:-1], pts[1:]], axis=1)
    mid = (fr[:-1] + fr[1:]) / 2
    zone_of = np.searchsorted(zones.start.to_numpy(), mid, side="right") - 1
    zone_of[mid >= zones.end.iloc[-1]] = 0  # tail of the lap = main straight
    cols = [colour[winners.iloc[z][0]] for z in zone_of]
    ax.add_collection(LineCollection(segs, colors=cols, linewidths=12, capstyle="round",
                                     zorder=2))

    # Label each section beside its midpoint: offset along the track's normal, on the
    # side facing away from the circuit's centre.
    centre = xy.mean(axis=0)
    span = np.ptp(xy, axis=0).max()
    for k, z in zones.reset_index(drop=True).iterrows():
        f_mid = (z.start + z.end) / 2
        i = int(np.argmin(np.abs(frac - f_mid)))
        p = xy[i]
        tang = xy[min(i + 3, len(xy) - 1)] - xy[max(i - 3, 0)]
        normal = np.array([-tang[1], tang[0]]) / (np.linalg.norm(tang) + 1e-9)
        if np.dot(normal, p - centre) < 0:
            normal = -normal
        q = p + normal * span * 0.06
        if label_at and k in label_at:
            q = np.array(label_at[k])
        code = winners.iloc[k][1]
        ax.text(q[0], q[1], code, ha="center", va="center", fontsize=19, color=INK,
                fontweight="bold", zorder=4,
                bbox=dict(boxstyle="round,pad=0.25", fc=colour[winners.iloc[k][0]], ec="none"))
    pad = span * 0.12
    ax.set_xlim(xy[:, 0].min() - pad, xy[:, 0].max() + pad)
    ax.set_ylim(xy[:, 1].min() - pad, xy[:, 1].max() + pad)
    start = xy[0]
    ax.plot(*start, marker="s", ms=10, color=INK, zorder=5)

    # Section table.
    top = 0.355
    fig.text(0.07, top, "Section", fontsize=18, color=MUTED, fontweight="bold")
    fig.text(0.45, top, "Fastest", fontsize=18, color=MUTED, fontweight="bold")
    fig.text(0.76, top, "Avg speed" if speed else "Time", fontsize=18, color=MUTED, fontweight="bold", ha="right")
    fig.text(0.93, top, "Margin", fontsize=18, color=MUTED, fontweight="bold", ha="right")
    for k, col in enumerate(table.columns):
        s = table[col].sort_values(ascending=not speed)
        (name, code, team), t, gap = s.index[0], s.iloc[0], abs(s.iloc[1] - s.iloc[0])
        y = top - 0.034 * (k + 1)
        kind = "Straight" if zones.straight.iloc[k] else "Corners"
        label = names[k] if k < len(names) else f"{kind} {k + 1}"
        fig.text(0.07, y, label, fontsize=19, color=INK)
        fig.patches.append(plt.Rectangle((0.425, y - 0.002), 0.016, 0.016,
                                         transform=fig.transFigure, color=colour[name]))
        fig.text(0.45, y, name, fontsize=19, color=INK, fontweight="bold")
        value, margin = (f"{t:.1f} km/h", f"{gap:.2f} km/h") if speed else (f"{t:.3f}s",
                                                                            f"{gap:.3f}s")
        fig.text(0.76, y, value, fontsize=19, color=INK_2, ha="right")
        fig.text(0.93, y, margin, fontsize=19, color=INK_2, ha="right")
    notes = notes or ["Each driver's fastest valid lap  ·  Straights = full-throttle zones of the "
             "session's fastest lap",
             "Corners = everything between them  ·  Margin = gap to 2nd-fastest in that section",
             "Data: OpenF1 car telemetry  ·  ■ = start/finish line"]
    for i, n in enumerate(notes):
        fig.text(0.5, 0.058 - 0.022 * i, n, ha="center", fontsize=14, color=MUTED)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--lap-km", type=float, required=True)
    parser.add_argument("--sessions", nargs="+", default=["Practice 1", "Practice 2"])
    parser.add_argument("--sections", nargs="*", default=[])
    parser.add_argument("--event", default="", help='title text, e.g. "Mexico City GP 2026"')
    parser.add_argument("--quali-phase", type=int, choices=[1, 2, 3],
                        help="with --sessions Qualifying: only laps from Q1, Q2 or Q3")
    parser.add_argument("--exclude", nargs="+", default=[],
                        help="driver codes to leave out of the section ranking, e.g. LIN")
    parser.add_argument("--average", action="store_true",
                        help="rank sections by average speed over all clean laps "
                             "instead of each driver's fastest lap")
    parser.add_argument("--only", nargs="+", default=[],
                        help="driver codes to keep (everyone else is left out), e.g. VER HAM")
    args = parser.parse_args()
    out = HERE / "output"
    out.mkdir(exist_ok=True)
    short = {"Practice 1": "FP1", "Practice 2": "FP2", "Practice 3": "FP3"}
    for s in fetch("sessions", year=args.year, location=args.location):
        name = s["session_name"]
        if name not in args.sessions:
            continue
        window = None
        if args.quali_phase and name == "Qualifying":
            window = sc.quali_window(s["session_key"], args.quali_phase)
            short[name] = f"Q{args.quali_phase}"
        counts, notes = None, None
        if args.average:
            table, zones, ref, counts = average_section_speeds(s["session_key"], args.lap_km, window)
            notes = ["Average over each driver's clean laps (no lap 1, pit laps, or laps >7% off "
                     "their best; 10+ laps)",
                     "Straights = full-throttle zones of the fastest lap  ·  Margin = gap to 2nd",
                     "Data: OpenF1 car telemetry  ·  ■ = start/finish line"]
        else:
            table, zones, ref = section_times(s["session_key"], args.lap_km, window)
        names, label_at = args.sections, None
        if args.location in CIRCUITS:  # traced map: no position data needed
            frac, xy = traced_outline(args.location, zones.start.to_numpy(), zones.end.iloc[-1])
            names = names or CIRCUITS[args.location]["sections"]
            label_at = label_positions(args.location)
        else:
            frac, xy = outline(s["session_key"], ref)
        label = short.get(name, name)
        # With --exclude, draw the full map and the map without those drivers, sharing
        # one colour per driver so the two can be compared side by side.
        excluded = [c.upper() for c in args.exclude]
        variants = [(table, "", "")]
        if args.only:
            keep = [c.upper() for c in args.only]
            codes = table.index.get_level_values("Code")
            missing = sorted(set(keep) - set(codes))
            if missing:
                raise SystemExit(f"No valid lap for: {', '.join(missing)}")
            variants.append((table[codes.isin(keep)], "_only_" + "_".join(c.lower() for c in keep),
                             f" · only {', '.join(c for c in codes if c in keep)}"))
        elif excluded:
            codes = table.index.get_level_values("Code")
            dropped = table.index[codes.isin(excluded)].get_level_values("Driver").tolist()
            variants.append((table[~codes.isin(excluded)],
                             "_without_" + "_".join(c.lower() for c in excluded),
                             f" · without {', '.join(dropped)}"))
        colour = colours_for([v[0] for v in variants], args.average)
        stem = f"{args.year}_{args.location.replace(' ', '_').lower()}_{label.lower()}"
        for tbl, suffix, note in variants:
            path = out / f"{stem}_track_dominance{'_avg_speed' if args.average else ''}{suffix}.png"
            subtitle = ("Highest average speed in each section" if args.average
                        else "Fastest driver in each section") + (
                note or (f" · {args.event}" if args.event else ""))
            draw(path, f"TRACK DOMINANCE · {label.upper()}", subtitle,
                 tbl, zones, frac, xy, names, label_at, colour, speed=args.average, notes=notes)
            print("Saved", path)
        table = variants[-1][0]
        if counts:
            print("  laps averaged:", {k[1]: v for k, v in counts.items()})
        for k, col in enumerate(table.columns):
            s_ = table[col].sort_values(ascending=not args.average)
            print(f"  {names[k] if k < len(names) else k}: {s_.index[0][0]} "
                  f"{s_.iloc[0]:.3f} ({abs(s_.iloc[1] - s_.iloc[0]):.3f} ahead of "
                  f"{s_.index[1][0]})")


if __name__ == "__main__":
    main()
