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


def section_times(session_key, lap_km):
    """Per-driver time through each section (main straight parts merged)."""
    best = sc.fastest_laps(session_key)
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


def draw(path, title, subtitle, table, zones, frac, xy, names, label_at=None):
    winners = table.idxmin()
    order = list(dict.fromkeys(w[0] for w in winners))  # first-win order, fixed colours
    if len(order) > len(PALETTE):
        raise SystemExit("More section winners than palette colours.")
    colour = {d: PALETTE[i] for i, d in enumerate(order)}

    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
    fig.patch.set_facecolor(BG)
    fig.text(0.5, 0.955, title, ha="center", fontsize=40, color=INK, fontweight="bold")
    fig.text(0.5, 0.92, subtitle, ha="center", fontsize=21, color=INK_2)

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
    fig.text(0.76, top, "Time", fontsize=18, color=MUTED, fontweight="bold", ha="right")
    fig.text(0.93, top, "Margin", fontsize=18, color=MUTED, fontweight="bold", ha="right")
    for k, col in enumerate(table.columns):
        s = table[col].sort_values()
        (name, code, team), t, gap = s.index[0], s.iloc[0], s.iloc[1] - s.iloc[0]
        y = top - 0.034 * (k + 1)
        kind = "Straight" if zones.straight.iloc[k] else "Corners"
        label = names[k] if k < len(names) else f"{kind} {k + 1}"
        fig.text(0.07, y, label, fontsize=19, color=INK)
        fig.patches.append(plt.Rectangle((0.425, y - 0.002), 0.016, 0.016,
                                         transform=fig.transFigure, color=colour[name]))
        fig.text(0.45, y, name, fontsize=19, color=INK, fontweight="bold")
        fig.text(0.76, y, f"{t:.3f}s", fontsize=19, color=INK_2, ha="right")
        fig.text(0.93, y, f"{gap:.3f}s", fontsize=19, color=INK_2, ha="right")
    notes = ["Each driver's fastest valid lap  ·  Straights = full-throttle zones of the "
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
    args = parser.parse_args()
    out = HERE / "output"
    out.mkdir(exist_ok=True)
    short = {"Practice 1": "FP1", "Practice 2": "FP2", "Practice 3": "FP3"}
    for s in fetch("sessions", year=args.year, location=args.location):
        name = s["session_name"]
        if name not in args.sessions:
            continue
        table, zones, ref = section_times(s["session_key"], args.lap_km)
        names, label_at = args.sections, None
        if args.location in CIRCUITS:  # traced map: no position data needed
            frac, xy = traced_outline(args.location, zones.start.to_numpy(), zones.end.iloc[-1])
            names = names or CIRCUITS[args.location]["sections"]
            label_at = label_positions(args.location)
        else:
            frac, xy = outline(s["session_key"], ref)
        label = short.get(name, name)
        path = out / f"{args.year}_{args.location.replace(' ', '_').lower()}_{label.lower()}_track_dominance.png"
        draw(path, f"TRACK DOMINANCE · {label}",
             f"Fastest driver in each section{' · ' + args.event if args.event else ''}",
             table, zones, frac, xy, names, label_at)
        print("Saved", path)
        for k, col in enumerate(table.columns):
            s_ = table[col].sort_values()
            print(f"  {names[k] if k < len(names) else k}: {s_.index[0][0]} "
                  f"{s_.iloc[0]:.3f} (+{s_.iloc[1] - s_.iloc[0]:.3f} {s_.index[1][0]})")


if __name__ == "__main__":
    main()
