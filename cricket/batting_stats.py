"""Batting stats for one player from Cricsheet ball-by-ball JSON, optionally by venue.

Download and unzip Cricsheet data first (see cricket/README.md), e.g. T20 internationals
into cricket/data/t20s/. Then:

    python cricket/batting_stats.py --player "DJ Mitchell" --team "New Zealand" \
        --data cricket/data/t20s --venue Wellington

--venue matches any part of the venue or city name ("Wellington" covers both
"Sky Stadium" and its old name "Westpac Stadium", which Cricsheet records separately).
"""

import argparse
import glob
import json
from pathlib import Path

import pandas as pd

PHASES = [("Powerplay (1-6)", 0, 5), ("Middle (7-15)", 6, 14), ("Death (16-20)", 15, 19)]
NOT_DISMISSALS = {"retired hurt", "retired not out"}


def load_balls(data_dirs, player, team=None, venue=None):
    """Every ball the player faced, plus one row per innings they batted in."""
    balls, innings = [], []
    for data_dir in data_dirs:
        for path in sorted(glob.glob(str(Path(data_dir) / "*.json"))):
            match = json.loads(Path(path).read_text())
            info = match["info"]
            if info.get("gender") != "male":
                continue
            ground = f'{info.get("venue", "")} {info.get("city", "")}'
            if venue and venue.lower() not in ground.lower():
                continue
            squads = info["players"]
            if not any(player in p and (team is None or t == team) for t, p in squads.items()):
                continue
            match_id = Path(path).stem
            date = info["dates"][0]
            opponent = next((t for t in info["teams"] if player not in squads[t]), "")
            for inn in match["innings"]:
                if inn.get("super_over") or (team and inn["team"] != team):
                    continue
                if player not in squads.get(inn["team"], []):
                    continue
                order, out_how, faced = [], None, False
                for over in inn["overs"]:
                    for ball in over["deliveries"]:
                        for name in (ball["batter"], ball["non_striker"]):
                            if name not in order:
                                order.append(name)
                        for w in ball.get("wickets", []):
                            if w["player_out"] == player:
                                out_how = w["kind"]
                        if ball["batter"] != player:
                            continue
                        faced = True
                        extras = ball.get("extras", {})
                        balls.append({
                            "match_id": match_id,
                            "over": over["over"],
                            "runs": ball["runs"]["batter"],
                            "legal": "wides" not in extras,  # no-balls count as faced
                        })
                if not faced and player not in order:
                    continue  # in the XI but did not bat
                innings.append({
                    "match_id": match_id,
                    "date": date,
                    "venue": info.get("venue", ""),
                    "opponent": opponent,
                    "position": order.index(player) + 1 if player in order else None,
                    "dismissal": out_how or "not out",
                })
    return pd.DataFrame(balls), pd.DataFrame(innings)


def matches_played(data_dirs, player, team=None, venue=None):
    """Matches the player was in the XI for (batted or not)."""
    count = 0
    for data_dir in data_dirs:
        for path in glob.glob(str(Path(data_dir) / "*.json")):
            info = json.loads(Path(path).read_text())["info"]
            if info.get("gender") != "male":
                continue
            ground = f'{info.get("venue", "")} {info.get("city", "")}'
            if venue and venue.lower() not in ground.lower():
                continue
            if any(player in p and (team is None or t == team) for t, p in info["players"].items()):
                count += 1
    return count


def summarise(balls, innings, matches):
    """The headline batting numbers as an ordered dict of label -> value."""
    legal = balls[balls.legal]
    runs = int(balls.runs.sum())
    faced = len(legal)
    fours = int((balls.runs == 4).sum())
    sixes = int((balls.runs == 6).sum())
    dots = int((legal.runs == 0).sum())
    singles = int((legal.runs == 1).sum())
    outs = int((~innings.dismissal.isin(["not out", *NOT_DISMISSALS])).sum())
    per_inn = balls.groupby("match_id").runs.sum().reindex(innings.match_id, fill_value=0)
    pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731

    best = innings.assign(score=per_inn.values).sort_values("score", ascending=False).iloc[0]
    high = f"{int(best.score)}{'*' if best.dismissal == 'not out' else ''}"
    return {
        "Matches": matches,
        "Innings": len(innings),
        "Not outs": len(innings) - outs,
        "Runs": runs,
        "Balls faced": faced,
        "Strike rate": pct(runs, faced),
        "Average": round(runs / outs, 2) if outs else None,
        "Highest score": high,
        "50s": int((per_inn >= 50).sum()),
        "30+ scores": int((per_inn >= 30).sum()),
        "Ducks": int(((per_inn == 0) & (innings.dismissal.values != "not out")).sum()),
        "Fours": fours,
        "Sixes": sixes,
        "Boundary % (4s+6s / balls)": pct(fours + sixes, faced),
        "Runs from boundaries %": pct(4 * fours + 6 * sixes, runs),
        "Balls per boundary": round(faced / (fours + sixes), 1) if fours + sixes else None,
        "Dot balls": dots,
        "Dot ball %": pct(dots, faced),
        "Singles": singles,
        "Rotation % (balls scored 1-3 off)": pct(int(legal.runs.between(1, 3).sum()), faced),
        "Balls per innings": round(faced / len(innings), 1) if len(innings) else None,
        "Balls per dismissal": round(faced / outs, 1) if outs else None,
    }


def phase_table(balls):
    rows = []
    for name, lo, hi in PHASES:
        b = balls[balls.over.between(lo, hi)]
        legal = b[b.legal]
        n = len(legal)
        rows.append({
            "Phase": name,
            "Runs": int(b.runs.sum()),
            "Balls": n,
            "Strike rate": round(100 * b.runs.sum() / n, 1) if n else None,
            "4s": int((b.runs == 4).sum()),
            "6s": int((b.runs == 6).sum()),
            "Dot %": round(100 * (legal.runs == 0).sum() / n, 1) if n else None,
        })
    return pd.DataFrame(rows)


def innings_table(balls, innings):
    g = balls.groupby("match_id")
    per = pd.DataFrame({
        "Runs": g.runs.sum(),
        "Balls": balls[balls.legal].groupby("match_id").size(),
        "4s": g.runs.apply(lambda r: (r == 4).sum()),
        "6s": g.runs.apply(lambda r: (r == 6).sum()),
    })
    t = innings.join(per, on="match_id").fillna({"Runs": 0, "Balls": 0, "4s": 0, "6s": 0})
    t["Strike rate"] = (100 * t.Runs / t.Balls.where(t.Balls > 0)).round(1)
    cols = ["date", "opponent", "venue", "position", "Runs", "Balls", "4s", "6s",
            "Strike rate", "dismissal"]
    return t[cols].sort_values("date").astype({"Runs": int, "Balls": int, "4s": int, "6s": int})


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--player", required=True, help='Cricsheet name, e.g. "DJ Mitchell"')
    parser.add_argument("--team", help='only innings for this team, e.g. "New Zealand"')
    parser.add_argument("--data", nargs="+", required=True, help="folders of Cricsheet JSON")
    parser.add_argument("--venue", help="part of the venue or city name")
    parser.add_argument("--out", type=Path, help="write the summary and innings to this .xlsx")
    args = parser.parse_args()

    balls, innings = load_balls(args.data, args.player, args.team, args.venue)
    if innings.empty:
        raise SystemExit("No innings found - check the player name, team and venue.")
    matches = matches_played(args.data, args.player, args.team, args.venue)
    summary = pd.Series(summarise(balls, innings, matches), name="Value")
    phases = phase_table(balls)
    by_innings = innings_table(balls, innings)

    pd.set_option("display.width", 200)
    print(summary.to_string())
    print("\nBy phase\n" + phases.to_string(index=False))
    print("\nBy innings\n" + by_innings.to_string(index=False))
    if args.out:
        with pd.ExcelWriter(args.out) as xl:
            summary.to_frame().to_excel(xl, sheet_name="Summary")
            phases.to_excel(xl, sheet_name="By phase", index=False)
            by_innings.to_excel(xl, sheet_name="By innings", index=False)
        print(f"\nSaved {args.out}")


if __name__ == "__main__":
    main()
