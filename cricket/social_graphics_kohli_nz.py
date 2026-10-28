"""Instagram / YouTube Shorts graphics: Virat Kohli in ODIs vs New Zealand.

Makes 7 vertical Reel/Short slides (1080x1920) and 4 carousel slides (1080x1350,
Instagram 4:5) in cricket/output/social/. Every number is computed from the
Cricsheet ODI data (cricket/data/odis/), so re-running after new matches updates
the graphics.

    python cricket/social_graphics_kohli_nz.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

import pandas as pd  # noqa: E402

from batter_splits import NOT_OUT, load  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "output" / "social"
NZ_CITIES = ["Auckland", "Hamilton", "Mount Maunganui", "Napier", "Wellington",
             "Christchurch", "Dunedin", "Nelson", "Queenstown", "Whangarei", "Lincoln",
             "New Plymouth", "Rangiora"]
BOWLERS = {"JA Duffy": "Jacob Duffy", "MJ Henry": "Matt Henry", "KA Jamieson": "Kyle Jamieson",
           "MJ Santner": "Mitchell Santner", "LH Ferguson": "Lockie Ferguson",
           "KDC Clarke": "Kristian Clarke"}

BG = "#0B1426"
PANEL = "#16223A"
INK = "#FFFFFF"
INK_2 = "#C9D3E3"
MUTED = "#8A97AD"
ACCENT = "#FFB000"
BAR = "#3987E5"
FONT = "Liberation Sans"
plt.rcParams["font.family"] = FONT


# ---------------------------------------------------------------- numbers ---
def split_stats(balls, innings):
    legal = balls[balls.legal == "Yes"]
    runs = int(balls.runs.sum())
    per = balls.groupby("match_id").runs.sum()
    inn = innings.assign(score=innings.match_id.map(per).fillna(0).astype(int))
    outs = int((~inn.dismissal.isin(NOT_OUT)).sum())
    top = inn.sort_values("score", ascending=False).iloc[0]
    return {
        "matches": None, "innings": len(inn), "runs": runs, "balls": len(legal),
        "sr": 100 * runs / len(legal), "avg": runs / outs,
        "hs": f"{top.score}{'*' if top.dismissal in NOT_OUT else ''}",
        "100s": int((inn.score >= 100).sum()),
        "50s": int(((inn.score >= 50) & (inn.score < 100)).sum()),
        "bdry": 100 * balls.runs.isin([4, 6]).sum() / len(legal),
        "dot": 100 * (legal.runs == 0).mean(),
    }


def bowler_stats(balls, bowler):
    b = balls[balls.bowler == bowler]
    legal = b[b.legal == "Yes"]
    outs = int(b.bowler_wicket.sum())
    runs = int(b.runs.sum())
    return {
        "innings": int(b.first_vs_bowler.sum()), "runs": runs, "balls": len(legal),
        "sr": 100 * runs / len(legal), "outs": outs,
        "avg": runs / outs if outs else None, "dot": 100 * (legal.runs == 0).mean(),
        "bdry": int(b.runs.isin([4, 6]).sum()),
    }


def compute():
    balls, innings, matches, _ = load([HERE / "data" / "odis"], "V Kohli", "India", NZ_CITIES)
    s = {
        "nz_home": split_stats(balls[balls.in_host == "Yes"], innings[innings.in_host == "Yes"]),
        "vs_nz": split_stats(balls[balls.opponent == "New Zealand"],
                             innings[innings.opponent == "New Zealand"]),
        "career": split_stats(balls, innings),
    }
    s["nz_home"]["matches"] = int((matches.in_host == "Yes").sum())
    s["vs_nz"]["matches"] = int((matches.opponent == "New Zealand").sum())
    s["career"]["matches"] = len(matches)
    s["bowlers"] = {name: bowler_stats(balls, code) for code, name in BOWLERS.items()}
    s["data_to"] = pd.Timestamp(matches.date.max()).strftime("%-d %b %Y")
    return s


# ---------------------------------------------------------------- drawing ---
def canvas(h):
    fig = plt.figure(figsize=(10.8, h / 100), dpi=100)
    fig.patch.set_facecolor(BG)
    return fig


def text(fig, x, y, s, size, color=INK, weight="normal", ha="center", **kw):
    fig.text(x, y, s, fontsize=size, color=color, fontweight=weight, ha=ha, va="center", **kw)


def kicker(fig, y, s):
    text(fig, 0.5, y, s.upper(), 30, ACCENT, "bold")


def footer(fig, data_to, y=0.205):
    text(fig, 0.5, y, f"Data: Cricsheet ball-by-ball  ·  Kohli's ODIs up to {data_to}", 20, MUTED)


def panel(fig, x, y, w, h):
    fig.patches.append(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.015",
        transform=fig.transFigure, facecolor=PANEL, edgecolor="none"))


def stat_block(fig, x, y, value, label, size=96):
    text(fig, x, y, value, size, ACCENT, "bold")
    text(fig, x, y - 0.025 - size / 4800, label, 28, INK_2)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, facecolor=BG)
    plt.close(fig)


# Reel slides keep content between y=0.20 and y=0.85 (clear of app UI).
def reel_slides(s):
    b, vs, home, car = s["bowlers"], s["vs_nz"], s["nz_home"], s["career"]
    sant = b["Mitchell Santner"]

    fig = canvas(1920)
    kicker(fig, 0.80, "Virat Kohli in ODIs")
    text(fig, 0.5, 0.645, "SANTNER'S", 110, INK, "bold")
    text(fig, 0.5, 0.56, f"{sant['balls']} BALLS", 124, ACCENT, "bold")
    text(fig, 0.5, 0.42, "The New Zealand bowler who\nquietly shut Kohli down", 44, INK_2,
         linespacing=1.4)
    footer(fig, s["data_to"])
    save(fig, "reel_01_hook.png")

    fig = canvas(1920)
    kicker(fig, 0.80, "vs New Zealand · all venues")
    stat_block(fig, 0.5, 0.67, f"{vs['runs']:,}", "runs")
    stat_block(fig, 0.27, 0.49, f"{vs['avg']:.1f}", "average", 84)
    stat_block(fig, 0.73, 0.49, f"{vs['100s']}", "hundreds", 84)
    text(fig, 0.5, 0.33, f"{vs['matches']} ODIs  ·  SR {vs['sr']:.1f}  ·  HS {vs['hs']}", 34, INK_2)
    footer(fig, s["data_to"])
    save(fig, "reel_02_vs_nz.png")

    fig = canvas(1920)
    kicker(fig, 0.80, "In New Zealand")
    text(fig, 0.5, 0.735, "He slows down", 56, INK, "bold")
    stat_block(fig, 0.27, 0.60, f"{home['avg']:.1f}", "average", 84)
    stat_block(fig, 0.73, 0.60, f"{home['sr']:.1f}", "strike rate", 84)
    stat_block(fig, 0.5, 0.43, f"{home['dot']:.1f}%", "of balls are dots")
    text(fig, 0.5, 0.30, f"{home['matches']} ODIs  ·  {home['runs']} runs  ·  HS {home['hs']}",
         34, INK_2)
    footer(fig, s["data_to"])
    save(fig, "reel_03_in_nz.png")

    f = b["Lockie Ferguson"]
    fig = canvas(1920)
    kicker(fig, 0.80, "vs Lockie Ferguson")
    text(fig, 0.5, 0.71, "Pace doesn't scare him", 56, INK, "bold")
    stat_block(fig, 0.5, 0.56, f"{f['sr']:.1f}", "strike rate", 170)
    text(fig, 0.5, 0.40, f"{f['runs']} runs off {f['balls']} balls\n"
         f"{f['bdry']} boundaries  ·  out {f['outs']} time{'s' if f['outs'] != 1 else ''}",
         38, INK_2, linespacing=1.5)
    footer(fig, s["data_to"])
    save(fig, "reel_04_ferguson.png")

    h, j = b["Matt Henry"], b["Kyle Jamieson"]
    fig = canvas(1920)
    kicker(fig, 0.80, "Henry & Jamieson")
    text(fig, 0.5, 0.735, "They keep him quiet", 56, INK, "bold")
    for x, name, d in ((0.27, "Matt Henry", h), (0.73, "Kyle Jamieson", j)):
        panel(fig, x - 0.21, 0.37, 0.42, 0.31)
        text(fig, x, 0.635, name, 34, INK, "bold")
        text(fig, x, 0.555, f"{d['dot']:.0f}%", 110, ACCENT, "bold")
        text(fig, x, 0.495, "dot balls", 28, INK_2)
        text(fig, x, 0.42, f"{d['runs']} off {d['balls']}  ·  out {d['outs']}", 28, INK_2)
    text(fig, 0.5, 0.30, f"Kohli's career dot-ball rate: {car['dot']:.1f}%", 32, MUTED)
    footer(fig, s["data_to"])
    save(fig, "reel_05_henry_jamieson.png")

    fig = canvas(1920)
    kicker(fig, 0.80, "vs Mitchell Santner")
    text(fig, 0.5, 0.71, "The real problem", 56, INK, "bold")
    stat_block(fig, 0.5, 0.56, f"{sant['sr']:.1f}", "strike rate", 170)
    text(fig, 0.5, 0.40, f"{sant['runs']} runs off {sant['balls']} balls\n"
         f"only {sant['bdry']} boundaries  ·  out {sant['outs']} times", 38, INK_2,
         linespacing=1.5)
    text(fig, 0.5, 0.30, f"Kohli's career ODI strike rate: {car['sr']:.1f}", 32, MUTED)
    footer(fig, s["data_to"])
    save(fig, "reel_06_santner.png")

    d, c = b["Jacob Duffy"], b["Kristian Clarke"]
    fig = canvas(1920)
    kicker(fig, 0.82, "The new threats")
    text(fig, 0.5, 0.715, "WHO GETS\nKOHLI NEXT?", 90, INK, "bold", linespacing=1.1)
    for x, name, v in ((0.27, "Jacob Duffy", d), (0.73, "Kristian Clarke", c)):
        panel(fig, x - 0.21, 0.40, 0.42, 0.20)
        text(fig, x, 0.565, name, 34, INK, "bold")
        text(fig, x, 0.495, f"{v['outs']} out", 72, ACCENT, "bold")
        text(fig, x, 0.435, f"in {v['balls']} balls", 30, INK_2)
    text(fig, 0.5, 0.32, "Comment below", 48, ACCENT, "bold")
    footer(fig, s["data_to"])
    save(fig, "reel_07_question.png")


# Carousel slides: 1080x1350 (Instagram portrait 4:5).
def table(fig, top, headers, rows, col_x, highlight_col=None, row_h=0.062, size=30,
          header_size=24):
    for x, h in zip(col_x, headers):
        text(fig, x, top, h, header_size, MUTED, "bold", ha="left" if x == col_x[0] else "center")
    for i, row in enumerate(rows):
        y = top - (i + 1) * row_h
        if i % 2 == 0:
            panel(fig, 0.05, y - row_h / 2, 0.90, row_h)
        for j, (x, v) in enumerate(zip(col_x, row)):
            color = ACCENT if j == highlight_col else INK
            text(fig, x, y, v, size, color if j else INK, "bold" if j == 0 else "normal",
                 ha="left" if j == 0 else "center")


def carousel_slides(s):
    vs, home, car, b = s["vs_nz"], s["nz_home"], s["career"], s["bowlers"]

    fig = canvas(1350)
    kicker(fig, 0.78, "ODI numbers")
    text(fig, 0.5, 0.60, "KOHLI\nvs NEW ZEALAND", 78, INK, "bold", linespacing=1.15)
    text(fig, 0.5, 0.40, "In NZ  ·  vs NZ  ·  vs 6 Kiwi bowlers", 36, INK_2)
    text(fig, 0.5, 0.28, "Swipe →", 40, ACCENT, "bold")
    footer(fig, s["data_to"], y=0.08)
    save(fig, "carousel_01_cover.png")

    fig = canvas(1350)
    kicker(fig, 0.92, "Kohli in ODIs: the splits")
    rows = [
        ("Matches", home["matches"], vs["matches"], car["matches"]),
        ("Runs", f"{home['runs']:,}", f"{vs['runs']:,}", f"{car['runs']:,}"),
        ("Average", f"{home['avg']:.1f}", f"{vs['avg']:.1f}", f"{car['avg']:.1f}"),
        ("Strike rate", f"{home['sr']:.1f}", f"{vs['sr']:.1f}", f"{car['sr']:.1f}"),
        ("100s / 50s", f"{home['100s']} / {home['50s']}", f"{vs['100s']} / {vs['50s']}",
         f"{car['100s']} / {car['50s']}"),
        ("Highest", home["hs"], vs["hs"], car["hs"]),
        ("Boundary %", f"{home['bdry']:.1f}%", f"{vs['bdry']:.1f}%", f"{car['bdry']:.1f}%"),
        ("Dot ball %", f"{home['dot']:.1f}%", f"{vs['dot']:.1f}%", f"{car['dot']:.1f}%"),
    ]
    table(fig, 0.80, ["", "In NZ", "vs NZ", "Career"], [tuple(map(str, r)) for r in rows],
          [0.08, 0.50, 0.69, 0.87], row_h=0.075, size=34)
    text(fig, 0.5, 0.115, "Boundary % = (4s + 6s) ÷ balls faced", 22, MUTED)
    footer(fig, s["data_to"], y=0.07)
    save(fig, "carousel_02_splits.png")

    fig = canvas(1350)
    kicker(fig, 0.92, "Kohli vs the Kiwi bowlers")
    order = sorted(b.items(), key=lambda kv: kv[1]["balls"], reverse=True)
    rows = [(name, str(v["innings"]), f"{v['runs']} ({v['balls']})", f"{v['sr']:.1f}",
             str(v["outs"]), f"{v['dot']:.0f}%", f"{100 * v['bdry'] / v['balls']:.0f}%")
            for name, v in order]
    table(fig, 0.80, ["Bowler", "Inns", "Runs (balls)", "SR", "Outs", "Dot %", "Bdry %"],
          rows, [0.07, 0.385, 0.505, 0.625, 0.715, 0.805, 0.905], row_h=0.085, size=26,
          header_size=20)
    text(fig, 0.5, 0.19, "Bdry % = (4s + 6s) ÷ balls faced", 22, MUTED)
    text(fig, 0.5, 0.16, "Outs = wickets credited to the bowler (run outs excluded)", 22, MUTED)
    text(fig, 0.5, 0.13, "Duffy (5 balls) and Clarke (52 balls): small samples", 22, MUTED)
    footer(fig, s["data_to"], y=0.07)
    save(fig, "carousel_03_bowlers.png")

    fig = canvas(1350)
    kicker(fig, 0.92, "Kohli's strike rate by bowler")
    ax = fig.add_axes([0.33, 0.17, 0.58, 0.66])
    ax.set_facecolor(BG)
    items = sorted(b.items(), key=lambda kv: kv[1]["sr"])
    names = [n for n, _ in items]
    srs = [v["sr"] for _, v in items]
    ax.barh(names, srs, color=BAR, height=0.56)
    ax.axvline(car["sr"], color=ACCENT, lw=2, ls=(0, (4, 3)))
    ax.text(car["sr"], len(names) - 0.35, f"Career {car['sr']:.1f}", color=ACCENT, fontsize=22,
            ha="center", va="bottom", fontweight="bold")
    for y, (name, v) in enumerate(items):
        ax.text(v["sr"] + 2, y, f"{v['sr']:.1f}", va="center", color=INK, fontsize=24)
        ax.text(-4, y - 0.36, f"{v['balls']} balls", va="center", ha="right", color=MUTED,
                fontsize=17)
    ax.set_xlim(0, max(srs) * 1.18)
    ax.tick_params(axis="y", colors=INK, labelsize=24, length=0, pad=12)
    ax.tick_params(axis="x", colors=MUTED, labelsize=18)
    ax.grid(axis="x", color="#2A3854", lw=1)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_visible(False)
    text(fig, 0.5, 0.115, "Runs per 100 balls faced from each bowler, ODIs, all venues", 22, MUTED)
    footer(fig, s["data_to"], y=0.07)
    save(fig, "carousel_04_strike_rate_chart.png")


def main():
    s = compute()
    reel_slides(s)
    carousel_slides(s)
    print("Saved", len(list(OUT.glob("*.png"))), "images to", OUT)


if __name__ == "__main__":
    main()
