"""Excel list of stints that ran past the pit window, with race positions around them.

For each exceeded stint (see pit_windows.py): grid position, position at the start of
the stint, just before the stop (start of the in-lap), three laps after the stop, and
the finishing position. Places gained are Excel formulas over those columns.

    python f1/exceeded_positions.py --year 2026
"""

import argparse

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import pit_windows as pw
from practice_race_pace import HERE, fetch

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


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
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
    return df


if __name__ == "__main__":
    main()
