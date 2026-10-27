"""Write a player's batting data to Excel, with the summary built from formulas.

Sheets:
  Summary   - headline stats, every one a formula over the sheets below
  By Phase  - powerplay / middle / death splits (formulas)
  Innings   - one row per innings (runs, balls, 4s, 6s, dots are formulas over Balls)
  Balls     - every ball the player faced (the raw data)
"""

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

FONT = "Arial"
HEADER_FILL = PatternFill("solid", start_color="1C5CAB")
INPUT_FILL = PatternFill("solid", start_color="FFF2CC")
PHASES = [("Powerplay (1-6)", 1, 6), ("Middle (7-15)", 7, 15), ("Death (16-20)", 16, 20)]


def _phase(over_number):
    return next(name for name, lo, hi in PHASES if lo <= over_number <= hi)


def _header(ws, headers, widths):
    ws.append(headers)
    for c, (h, w) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"


def write_workbook(path, title, balls, innings, matches):
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    phase_ws = wb.create_sheet("By Phase")
    inn_ws = wb.create_sheet("Innings")
    ball_ws = wb.create_sheet("Balls")

    # Balls: raw data, one row per ball faced.
    _header(ball_ws, ["Match ID", "Date", "Opponent", "Over", "Phase", "Runs off bat",
                      "Legal ball"], [12, 12, 16, 8, 16, 12, 10])
    balls = balls.sort_values(["date", "match_id"], kind="stable")
    for b in balls.itertuples():
        over = int(b.over) + 1  # Cricsheet overs start at 0
        ball_ws.append([str(b.match_id), b.date, b.opponent, over, _phase(over),
                        int(b.runs), "Yes" if b.legal else "No"])
    nb = max(len(balls) + 1, 2)
    B = lambda col: f"Balls!${col}$2:${col}${nb}"  # noqa: E731

    # Innings: details as values, numbers as formulas over Balls.
    _header(inn_ws, ["Match ID", "Date", "Opponent", "Venue", "Batting position",
                     "Runs", "Balls", "4s", "6s", "Dot balls", "Strike rate",
                     "Dismissal", "Out (1 = yes)"],
            [12, 12, 16, 26, 10, 8, 8, 6, 6, 9, 10, 14, 10])
    innings = innings.sort_values("date", kind="stable")
    for r, i in enumerate(innings.itertuples(), start=2):
        inn_ws.append([
            str(i.match_id), i.date, i.opponent, i.venue,
            None if i.position is None else int(i.position),
            f'=SUMIFS({B("F")},{B("A")},$A{r})',
            f'=COUNTIFS({B("A")},$A{r},{B("G")},"Yes")',
            f'=COUNTIFS({B("A")},$A{r},{B("F")},4)',
            f'=COUNTIFS({B("A")},$A{r},{B("F")},6)',
            f'=COUNTIFS({B("A")},$A{r},{B("G")},"Yes",{B("F")},0)',
            f'=IF(G{r}=0,"",F{r}/G{r}*100)',
            i.dismissal,
            f'=IF(OR(L{r}="not out",L{r}="retired hurt",L{r}="retired not out"),0,1)',
        ])
        inn_ws.cell(row=r, column=11).number_format = "0.0"
    ni = max(len(innings) + 1, 2)
    I = lambda col: f"Innings!${col}$2:${col}${ni}"  # noqa: E731

    # Summary: every stat is a formula. Row numbers are fixed so formulas can refer back.
    summary["A1"] = title
    summary["A1"].font = Font(name=FONT, bold=True, size=13)
    summary["A2"] = "Source: Cricsheet ball-by-ball data (cricsheet.org). Men's matches only."
    summary["A2"].font = Font(name=FONT, italic=True, color="555555")
    summary.append([])
    summary.append(["Stat", "Value", "How it's calculated"])
    for c in range(1, 4):
        cell = summary.cell(row=4, column=c)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL

    legal = f'{B("G")},"Yes"'
    rows = [
        ("Matches", matches, "Matches in the playing XI (incl. did not bat)", None),
        ("Innings", f"=COUNTA({I('A')})", "Innings batted", None),
        ("Not outs", "=B6-B26", "Innings − dismissals", None),
        ("Runs", f"=SUM({I('F')})", "Runs off the bat", None),
        ("Balls faced", f"=COUNTIFS({legal})", "Legal balls (wides excluded, no-balls count)", None),
        ("Strike rate", '=IF(B9=0,"",B8/B9*100)', "Runs ÷ balls × 100", "0.0"),
        ("Average", '=IF(B26=0,"",B8/B26)', "Runs ÷ dismissals", "0.00"),
        ("Highest score",
         f'=MAX({I("F")})&IF(COUNTIFS({I("F")},MAX({I("F")}),{I("M")},0)>0,"*","")',
         "* = not out", None),
        ("50s", f'=COUNTIF({I("F")},">=50")', "Innings of 50+", None),
        ("30+ scores", f'=COUNTIF({I("F")},">=30")', "Innings of 30+", None),
        ("Ducks", f'=COUNTIFS({I("F")},0,{I("M")},1)', "Out for 0", None),
        ("Fours", f"=COUNTIF({B('F')},4)", "", None),
        ("Sixes", f"=COUNTIF({B('F')},6)", "", None),
        ("Boundary % (4s+6s)", '=IF(B9=0,"",(B16+B17)/B9)', "(4s + 6s) ÷ balls", "0.0%"),
        ("Runs from boundaries %", '=IF(B8=0,"",(4*B16+6*B17)/B8)', "Boundary runs ÷ runs", "0.0%"),
        ("Balls per boundary", '=IF(B16+B17=0,"",B9/(B16+B17))', "Balls ÷ (4s + 6s)", "0.0"),
        ("Dot balls", f"=COUNTIFS({legal},{B('F')},0)", "Legal balls with no runs off the bat", None),
        ("Dot ball %", '=IF(B9=0,"",B21/B9)', "Dot balls ÷ balls", "0.0%"),
        ("Singles", f"=COUNTIFS({legal},{B('F')},1)", "", None),
        ("Rotation % (1-3 runs)", f'=IF(B9=0,"",COUNTIFS({legal},{B("F")},">=1",{B("F")},"<=3")/B9)',
         "Balls scored 1, 2 or 3 off ÷ balls", "0.0%"),
        ("Balls per innings", '=IF(B6=0,"",B9/B6)', "", "0.0"),
        ("Dismissals", f"=SUM({I('M')})", "", None),
        ("Balls per dismissal", '=IF(B26=0,"",B9/B26)', "", "0.0"),
    ]
    for r, (label, value, note, fmt) in enumerate(rows, start=5):
        summary.cell(row=r, column=1, value=label)
        cell = summary.cell(row=r, column=2, value=value)
        summary.cell(row=r, column=3, value=note).font = Font(name=FONT, color="555555")
        if fmt:
            cell.number_format = fmt
        cell.alignment = Alignment(horizontal="right")
    summary["B5"].font = Font(name=FONT, color="0000FF")
    summary["B5"].fill = INPUT_FILL
    summary["B5"].comment = Comment(
        "Counted from Cricsheet line-ups: matches where the player was in the XI, "
        "including any where they did not bat.", "Claude")
    assert summary["A26"].value == "Dismissals"  # formulas above refer to B26
    for col, w in (("A", 26), ("B", 12), ("C", 46)):
        summary.column_dimensions[col].width = w

    # By Phase: formulas over Balls.
    _header(phase_ws, ["Phase", "Runs", "Balls", "Strike rate", "4s", "6s", "Dot balls",
                       "Dot ball %", "Boundary %"], [18, 8, 8, 10, 6, 6, 9, 10, 10])
    for r, (name, _, _) in enumerate(PHASES, start=2):
        p = f'{B("E")},$A{r}'
        phase_ws.append([
            name,
            f"=SUMIFS({B('F')},{p})",
            f'=COUNTIFS({p},{legal})',
            f'=IF(C{r}=0,"",B{r}/C{r}*100)',
            f"=COUNTIFS({p},{B('F')},4)",
            f"=COUNTIFS({p},{B('F')},6)",
            f'=COUNTIFS({p},{legal},{B("F")},0)',
            f'=IF(C{r}=0,"",G{r}/C{r})',
            f'=IF(C{r}=0,"",(E{r}+F{r})/C{r})',
        ])
        phase_ws.cell(row=r, column=4).number_format = "0.0"
        phase_ws.cell(row=r, column=8).number_format = "0.0%"
        phase_ws.cell(row=r, column=9).number_format = "0.0%"

    for ws in wb:
        for row in ws.iter_rows():
            for cell in row:
                if cell.font.name != FONT:
                    f = cell.font
                    cell.font = Font(name=FONT, bold=f.bold, italic=f.italic,
                                     color=f.color, size=f.size)
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
