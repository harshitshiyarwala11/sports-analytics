"""Sector-leader graphics: circuit coloured by the fastest driver in each timing sector.

Makes one 1080x1350 image per view, sharing one colour per driver:
  * Q3 - sector times from each driver's fastest Q3 lap
  * Race - sector times from each driver's fastest race lap
  * Race average - mean sector times over each driver's clean race laps

    python f1/sector_graphics.py --year 2026 --location "Mexico City" \
        --event "Mexico City GP 2026"
"""

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

import straights_vs_corners as sc  # noqa: E402
from circuits import CIRCUITS  # noqa: E402
from practice_race_pace import HERE, SECTORS, fetch  # noqa: E402
from track_dominance import BG, INK, INK_2, MUTED, PALETTE, TRACK, clean_laps  # noqa: E402

plt.rcParams["font.family"] = "Liberation Sans"


def sector_table(laps):
    """Driver x sector table (Driver, Code, Team index) from rows with sector times."""
    t = laps.set_index(["full_name", "name_acronym", "team_name"])[SECTORS]
    t.index = pd.MultiIndex.from_tuples(
        [(n.title(), c, team or "") for n, c, team in t.index], names=["Driver", "Code", "Team"])
    t.columns = ["Sector 1", "Sector 2", "Sector 3"]
    return t


def fastest_lap_sectors(session_key, window=None):
    return sector_table(sc.fastest_laps(session_key, window))


def average_sectors(session_key, min_laps=10):
    laps = clean_laps(session_key).dropna(subset=SECTORS)
    g = laps.groupby("driver_number").agg(n=("lap_number", "size"),
                                          **{s: (s, "mean") for s in SECTORS})
    g = g[g.n >= min_laps].reset_index()
    drivers = pd.DataFrame(fetch("drivers", session_key=session_key))
    g = g.merge(drivers[["driver_number", "full_name", "name_acronym", "team_name"]],
                on="driver_number")
    return sector_table(g), int(g.n.min()), int(g.n.max())


def sector_outline(name):
    """Traced circuit split into three timing sectors: list of (N, 2) point arrays."""
    c = CIRCUITS[name]
    pts = np.array(c["points"], dtype=float)
    # Densify, then cut at the waypoints nearest the sector lines.
    dense = []
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(int(np.linalg.norm(b - a)), 1)
        dense.append(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
    dense = np.vstack(dense + [pts[-1:]])
    cuts = [int(np.argmin(np.linalg.norm(dense - np.array(m), axis=1)))
            for m in c["sector_marks"]]
    parts = np.split(dense, cuts)
    parts = [np.vstack([p, q[:1]]) for p, q in zip(parts[:-1], parts[1:])] + [parts[-1]]
    for p in parts:
        p[:, 1] *= -1  # image y grows downwards
    return parts


def colours_for(tables):
    """One colour per sector winner across all graphics, in order of first appearance."""
    order = list(dict.fromkeys(t[col].idxmin()[0] for t in tables for col in t.columns))
    return {d: PALETTE[i] for i, d in enumerate(order)}


def draw(path, title, subtitle, table, parts, colour, note, label_at=None):
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
    fig.patch.set_facecolor(BG)
    fig.text(0.5, 0.955, title, ha="center", fontsize=40, color=INK, fontweight="bold")
    fig.text(0.5, 0.92, subtitle, ha="center", fontsize=21, color=INK_2)

    ax = fig.add_axes([0.06, 0.43, 0.88, 0.46])
    ax.set_facecolor(BG)
    ax.set_aspect("equal")
    ax.axis("off")
    allp = np.vstack(parts)
    ax.plot(allp[:, 0], allp[:, 1], color=TRACK, lw=22, solid_capstyle="round", zorder=1)
    centre = allp.mean(axis=0)
    span = np.ptp(allp, axis=0).max()
    for k, (p, col) in enumerate(zip(parts, table.columns)):
        win = table[col].idxmin()
        segs = np.stack([p[:-1], p[1:]], axis=1)
        ax.add_collection(LineCollection(segs, colors=colour[win[0]], linewidths=12,
                                         capstyle="round", zorder=2))
        i = len(p) // 2
        tang = p[min(i + 3, len(p) - 1)] - p[max(i - 3, 0)]
        normal = np.array([-tang[1], tang[0]]) / (np.linalg.norm(tang) + 1e-9)
        if np.dot(normal, p[i] - centre) < 0:
            normal = -normal
        q = p[i] + normal * span * 0.075
        if label_at and k in label_at:
            q = np.array(label_at[k])
        ax.text(q[0], q[1], f"S{k + 1}  {win[1]}", ha="center", va="center", fontsize=19,
                color=INK, fontweight="bold", zorder=4,
                bbox=dict(boxstyle="round,pad=0.3", fc=colour[win[0]], ec="none"))
    ax.plot(*parts[0][0], marker="s", ms=10, color=INK, zorder=5)
    pad = span * 0.12
    ax.set_xlim(allp[:, 0].min() - pad, allp[:, 0].max() + pad)
    ax.set_ylim(allp[:, 1].min() - pad, allp[:, 1].max() + pad)

    # Top three per sector.
    top = 0.395
    for k, col in enumerate(table.columns):
        s = table[col].sort_values()
        y0 = top - k * 0.105
        (name, code, team), t = s.index[0], s.iloc[0]
        fig.patches.append(plt.Rectangle((0.07, y0 - 0.006), 0.012, 0.03,
                                         transform=fig.transFigure, color=colour[name]))
        fig.text(0.095, y0, col.upper(), fontsize=17, color=MUTED, fontweight="bold")
        fig.text(0.095, y0 - 0.034, name, fontsize=26, color=INK, fontweight="bold")
        fig.text(0.93, y0 - 0.034, f"{t:.3f}s", fontsize=26, color=INK, fontweight="bold",
                 ha="right")
        rest = "     ".join(f"{i + 2}. {s.index[i + 1][1]} +{s.iloc[i + 1] - t:.3f}"
                           for i in range(min(2, len(s) - 1)))
        fig.text(0.095, y0 - 0.066, rest, fontsize=18, color=INK_2)
    fig.text(0.5, 0.058, note, ha="center", fontsize=14, color=MUTED)
    fig.text(0.5, 0.036, "Data: OpenF1 timing  ·  ■ = start/finish line", ha="center",
             fontsize=14, color=MUTED)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--event", default="")
    args = parser.parse_args()
    keys = {s["session_name"]: s["session_key"]
            for s in fetch("sessions", year=args.year, location=args.location)}
    q3 = fastest_lap_sectors(keys["Qualifying"], sc.quali_window(keys["Qualifying"], 3))
    race = fastest_lap_sectors(keys["Race"])
    race_avg, lo, hi = average_sectors(keys["Race"])
    views = [
        ("q3", "FASTEST SECTORS · Q3", "Fastest driver in each sector", q3,
         "Sector times from each driver's fastest Q3 lap"),
        ("race", "FASTEST SECTORS · RACE", "Fastest driver in each sector", race,
         "Sector times from each driver's fastest race lap"),
        ("race_avg", "AVERAGE SECTORS · RACE", "Lowest average time in each sector", race_avg,
         f"Mean sector times over {lo}-{hi} clean laps per driver "
         "(no lap 1, pit laps or laps >7% off their best)"),
    ]
    colour = colours_for([v[3] for v in views])
    parts = sector_outline(args.location)
    stem = f"{args.year}_{args.location.replace(' ', '_').lower()}"
    label_at = {k: (x, -y) for k, (x, y) in
                CIRCUITS[args.location].get("sector_labels", {}).items()}
    for slug, title, sub, table, note in views:
        path = HERE / "output" / f"{stem}_sectors_{slug}.png"
        draw(path, title, f"{sub} · {args.event}" if args.event else sub,
             table, parts, colour, note, label_at)
        print("Saved", path)


if __name__ == "__main__":
    main()
