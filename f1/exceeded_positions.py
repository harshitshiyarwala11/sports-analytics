"""Excel list of stints that ran past the pit window, with race positions around them.

For each exceeded stint (see pit_windows.py): grid position, position at the start of
the stint, just before the stop (start of the in-lap), three laps after the stop, and
the finishing position. Places gained are Excel formulas over those columns.

    python f1/exceeded_positions.py --year 2026
"""

import argparse

import matplotlib
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import pit_windows as pw
from practice_race_pace import HERE, fetch
from track_dominance import BG, DRIVER_COLOURS, INK, INK_2, MUTED

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

FONT = "Arial"
HEADER_FILL = PatternFill("solid", start_color="1C5CAB")
SETTLE_LAPS = 3


def position_lookup(session_key):
    """(driver, timestamp) -> race position, from OpenF1 position updates."""
    pos = pd.DataFrame(fetch("position", session_key=session_key))
    pos["t"] = pd.to_datetime(pos.date, format="ISO8601")
    pos = pos.sort_values("t")
    by_driver = {n: g for n, g in pos.groupby("driver_number")}

    def at(driver, t):
        g = by_driver.get(driver)
        if g is None or pd.isna(t):
            return None
        g = g[g.t <= t]
        return int(g.position.iloc[-1]) if len(g) else None

    grid = {n: int(g.position.iloc[0]) for n, g in by_driver.items()}
    return at, grid


def race_positions(session, stints):
    key = session["session_key"]
    at, grid = position_lookup(key)
    laps = pd.DataFrame(fetch("laps", session_key=key))
    laps["t"] = pd.to_datetime(laps.date_start, format="ISO8601")
    start_of = {(d, n): t for d, n, t in zip(laps.driver_number, laps.lap_number, laps.t)}
    result = pd.DataFrame(fetch("session_result", session_key=key))
    finish = {}
    for r in result.itertuples():
        if getattr(r, "dsq", False):
            finish[r.driver_number] = "DSQ"
        elif getattr(r, "dnf", False) or getattr(r, "dns", False) or pd.isna(r.position):
            finish[r.driver_number] = "DNF"
        else:
            finish[r.driver_number] = int(r.position)
    rows = []
    for s in stints.itertuples():
        d = s.driver_number
        t_start = start_of.get((d, int(s.lap_start)))
        start_pos = grid.get(d) if s.lap_start <= 1 else at(d, t_start)
        rows.append({
            "grid": grid.get(d),
            "pos_stint_start": start_pos,
            "pos_before_stop": at(d, start_of.get((d, int(s.lap_end)))),
            "pos_after_stop": at(d, start_of.get((d, int(s.lap_end) + SETTLE_LAPS))),
            "finish": finish.get(d, "DNF"),
        })
    return pd.DataFrame(rows, index=stints.index)


def write_workbook(path, df, year, n_races):
    wb = Workbook()
    ws = wb.active
    ws.title = "Exceeded stints"
    cols = [
        ("Date", "date", 11), ("Race", "race", 16), ("Driver", "driver", 8), ("Team", "team", 16),
        ("Tyre", "compound", 9), ("Stint laps", "laps_span", 10), ("Tyre life (laps)", "tyre_life", 9),
        ("Field window", "window", 11), ("Field median", "window_median", 9),
        ("Laps past median", "beyond_median", 9), ("Stopped under SC/VSC", "sc", 10),
        ("Grid", "grid", 6), ("Position at stint start", "pos_stint_start", 10),
        ("Position before stop", "pos_before_stop", 10),
        ("Position 3 laps after stop", "pos_after_stop", 10), ("Finish", "finish", 7),
    ]
    formulas = [("Places gained during stint", 10), ("Places lost at stop", 9),
                ("Places gained grid to finish", 10)]
    headers = [c[0] for c in cols] + [f[0] for f in formulas]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 45
    letter = {key: get_column_letter(i + 1) for i, (_, key, _) in enumerate(cols)}
    for r, row in enumerate(df.itertuples(), start=2):
        values = {
            "date": row.date, "race": row.race, "driver": row.driver, "team": row.team,
            "compound": row.compound.title(),
            "laps_span": f"{int(row.lap_start)}-{int(row.lap_end)}",
            "tyre_life": int(row.tyre_life),
            "window": f"{row.window_from:.0f}-{row.window_to:.0f}",
            "window_median": float(row.window_median),
            "beyond_median": float(row.beyond_median), "sc": "Yes" if row.under_sc else "No",
            "grid": row.grid, "pos_stint_start": row.pos_stint_start,
            "pos_before_stop": row.pos_before_stop, "pos_after_stop": row.pos_after_stop,
            "finish": row.finish,
        }
        for c, (_, key, _) in enumerate(cols, start=1):
            v = values[key]
            ws.cell(row=r, column=c, value=None if v is None or pd.isna(v) else v)
        S, B, A, G, F = (letter[k] for k in ("pos_stint_start", "pos_before_stop",
                                              "pos_after_stop", "grid", "finish"))
        base = len(cols)
        ws.cell(row=r, column=base + 1,
                value=f'=IF(OR({S}{r}="",{B}{r}=""),"",{S}{r}-{B}{r})')
        ws.cell(row=r, column=base + 2,
                value=f'=IF(OR({B}{r}="",{A}{r}=""),"",{A}{r}-{B}{r})')
        ws.cell(row=r, column=base + 3,
                value=f'=IF(OR({G}{r}="",NOT(ISNUMBER({F}{r}))),"",{G}{r}-{F}{r})')
    for i, (_, _, w) in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for i, (_, w) in enumerate(formulas, start=len(cols) + 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name=FONT)
            if cell.column > 4:
                cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = ws.dimensions

    notes = wb.create_sheet("Notes")
    lines = [
        f"Stints that ran past the pit window, {year} season ({n_races} races). Data: OpenF1.",
        "Field window: middle half (25th-75th percentile) of tyre life across completed "
        "green-flag stints on that compound in that race.",
        f"Exceeded: tyre life above the window and {pw.EXTRA_LAPS}+ laps past the field "
        "median. Tyre life = laps on the set when it came off.",
        "Grid: first position recorded in the race. Positions are race order at the start "
        "of that lap.",
        f"Position 3 laps after stop: race order {SETTLE_LAPS} laps after the in-lap, once "
        "the stop has settled.",
        "Places gained during stint = position at stint start minus position before the "
        "stop (positive = gained).",
        "Places lost at stop = position after the stop minus position before it "
        "(positive = lost).",
        "Places gained grid to finish = grid minus finish (blank if the driver did not "
        "finish).",
    ]
    for i, line in enumerate(lines, start=1):
        notes.cell(row=i, column=1, value=line).font = Font(name=FONT, bold=i == 1)
    notes.column_dimensions["A"].width = 120
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)


OUTCOMES = [("Gained", "#3DAF2C"), ("Same", "#8A97AD"), ("Lost", "#E53935"),
            ("Did not finish", "#3A4660")]
GRIDLINE = "#2A3854"
plt.rcParams["font.family"] = "Liberation Sans"


def outcomes(df):
    """Per driver: long stints by result at the finish vs position at the stint start."""
    fin = pd.to_numeric(df.finish, errors="coerce")
    change = df.pos_stint_start - fin
    df = df.assign(outcome=np.select([fin.isna(), change > 0, change == 0],
                                     ["Did not finish", "Gained", "Same"], "Lost"),
                   change=change)
    t = df.pivot_table(index="driver", columns="outcome", values="race", aggfunc="count",
                       fill_value=0)
    for name, _ in OUTCOMES:
        if name not in t:
            t[name] = 0
    t["Total"] = t[[n for n, _ in OUTCOMES]].sum(axis=1)
    t["Avg change"] = df.groupby("driver").change.mean()
    return t.sort_values(["Total", "Gained"], ascending=False)


def draw_outcomes(path, title, subtitle, t, highlight, notes, top_n=15):
    t = t.head(top_n).iloc[::-1]
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
    fig.patch.set_facecolor(BG)
    fig.text(0.5, 0.955, title, ha="center", fontsize=34, color=INK, fontweight="bold")
    fig.text(0.5, 0.922, subtitle, ha="center", fontsize=19, color=INK_2)
    ax = fig.add_axes([0.14, 0.30, 0.58, 0.57])
    ax.set_facecolor(BG)
    left = np.zeros(len(t))
    for name, colour in OUTCOMES:
        vals = t[name].to_numpy()
        ax.barh(t.index, vals, left=left, color=colour, height=0.62, edgecolor=BG,
                linewidth=2, label=name)
        for i, (v, l) in enumerate(zip(vals, left)):
            if v:
                ax.text(l + v / 2, i, f"{int(v)}", ha="center", va="center", fontsize=13,
                        color=INK if name in ("Did not finish", "Lost") else "#0B1426",
                        fontweight="bold")
        left += vals
    for i, (d, r) in enumerate(t.iterrows()):
        avg = "" if pd.isna(r["Avg change"]) else f"  ·  avg {r['Avg change']:+.1f}"
        ax.text(r.Total + 0.2, i, f"{int(r.Gained)} of {int(r.Total)} gained{avg}",
                va="center", fontsize=14, color=INK if d == highlight else INK_2,
                fontweight="bold" if d == highlight else "normal")
    ax.set_xlim(0, t.Total.max() * 1.75 + 0.5)
    ax.tick_params(axis="y", colors=INK, labelsize=16, length=0, pad=10)
    for lab in ax.get_yticklabels():
        if lab.get_text() == highlight:
            lab.set_fontweight("bold")
            lab.set_color(DRIVER_COLOURS.get(highlight, INK))
    ax.tick_params(axis="x", colors=MUTED, labelsize=13)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.grid(axis="x", color=GRIDLINE, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xlabel("long stints (past the pit window)", color=MUTED, fontsize=14)
    ax.legend(loc="upper center", bbox_to_anchor=(0.62, -0.09), frameon=False, ncol=4,
              fontsize=14, labelcolor=INK)
    for i, n in enumerate(notes):
        fig.text(0.07, 0.17 - 0.026 * i, n, fontsize=13.5, color=MUTED)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--driver", default="ANT", help="driver to highlight")
    args = parser.parse_args()
    sessions = [s for s in fetch("sessions", year=args.year, session_name="Race")
                if pd.Timestamp(s["date_end"]) < pd.Timestamp.now(tz="UTC")]
    frames = []
    for s in sessions:
        st = pw.race_stints(s)
        if not st.empty:
            frames.append(st.assign(session_key=s["session_key"]))
    st = pw.add_windows(pd.concat(frames, ignore_index=True))
    ex = st[st.exceeded].copy()
    by_session = {s["session_key"]: s for s in sessions}
    parts = [race_positions(by_session[k], g).join(g) for k, g in ex.groupby("session_key")]
    df = pd.concat(parts).sort_values(["date", "driver", "lap_start"])
    out = HERE / "output"
    out.mkdir(exist_ok=True)
    path = out / f"{args.year}_exceeded_stints_positions.xlsx"
    write_workbook(path, df, args.year, len(sessions))
    print(f"{len(df)} exceeded stints -> {path}")
    t = outcomes(df)
    notes = [f"{len(df)} stints that ran past the pit window, {args.year} season "
             f"({len(sessions)} races).",
             "Gained / same / lost = finishing position vs position at the start of the "
             "long stint.",
             "Avg = average places gained (finishers only). Data: OpenF1 positions & "
             "results."]
    png = out / f"{args.year}_long_stints_finish.png"
    draw_outcomes(png, "LONG STINTS: DID THEY PAY OFF?",
                  f"{args.year} season · position at the finish vs start of the long stint",
                  t, args.driver.upper(), notes)
    print("Saved", png)
    print(t.round(2).to_string())
    return df


if __name__ == "__main__":
    main()
