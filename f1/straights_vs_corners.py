"""Who is fastest on the straights and who is fastest through the corners?

Uses each driver's fastest valid lap of a session (deleted laps and out-laps
excluded) and its car telemetry from OpenF1 (speed/throttle at ~4 Hz):

1. The session's fastest lap is the reference. Where that car is at full throttle
   (>= 98%) the track counts as "straight"; everywhere else (braking, turning,
   traction) counts as "corner". Short zones under MIN_ZONE_M are merged into
   their neighbours so a flick of throttle doesn't create a fake straight.
2. Every driver's lap is mapped onto the same zones by fraction of lap distance,
   and the time spent in straight zones and in corner zones is measured.

Usage:
    python f1/straights_vs_corners.py --year 2026 --location "Mexico City" --lap-km 4.304
"""

import argparse
import re

import numpy as np
import pandas as pd

from practice_laps_to_excel import fetch_car_data
from practice_race_pace import SECTORS, fetch

FULL_THROTTLE = 98
MIN_ZONE_M = 100


def deleted_laps(session_key, laps):
    """(driver_number, lap_number) pairs deleted by race control.

    Race control counts laps one higher than OpenF1 (checked against every deletion
    that quotes a lap time). Deletions without a time are also matched by clock time,
    and both candidates are excluded.
    """
    bad = set()
    rc = pd.DataFrame(fetch("race_control", session_key=session_key))
    if rc.empty:
        return bad
    for r in rc[rc.message.str.contains("DELETED", na=False)].itertuples():
        m = re.match(r"CAR (\d+) \(\w+\) (?:TIME [\d:.]+ )?(?:LAP )?DELETED.* LAP (\d+)", r.message)
        if not m:
            continue
        n, lap = int(m[1]), int(m[2])
        bad.add((n, lap - 1))
        if "TIME" not in r.message:
            dl = laps[laps.driver_number == n].dropna(subset=["date_start"]).copy()
            if dl.empty:
                continue
            end = pd.to_datetime(dl.date_start, format="ISO8601") + pd.to_timedelta(
                dl.lap_duration.fillna(0), unit="s")
            bad.add((n, int(dl.iloc[(end - pd.Timestamp(r.date)).abs().argmin()].lap_number)))
    return bad


def fastest_laps(session_key):
    """Each driver's fastest valid lap, with name and team."""
    laps = pd.DataFrame(fetch("laps", session_key=session_key))
    drivers = pd.DataFrame(fetch("drivers", session_key=session_key))
    bad = deleted_laps(session_key, laps)
    ok = laps[~laps.is_pit_out_lap.fillna(False).astype(bool)].dropna(
        subset=["lap_duration", "date_start"] + SECTORS)
    ok = ok[[(d, n) not in bad for d, n in zip(ok.driver_number, ok.lap_number)]]
    best = ok.sort_values("lap_duration").drop_duplicates("driver_number")
    return best.merge(drivers[["driver_number", "full_name", "team_name"]], on="driver_number")


def trace(session_key, lap):
    """Telemetry for one lap: time from lap start, distance fraction, speed, throttle."""
    t0 = pd.Timestamp(lap.date_start)
    pad = pd.Timedelta(seconds=1)
    car = pd.DataFrame(fetch_car_data(session_key, lap.driver_number, t0 - pad,
                                      t0 + pd.Timedelta(seconds=lap.lap_duration) + pad))
    t = (pd.to_datetime(car.date, format="ISO8601") - t0).dt.total_seconds().to_numpy()
    order = np.argsort(t)
    t, v = t[order], car.speed.to_numpy()[order] / 3.6
    dist = np.concatenate([[0], np.cumsum((v[1:] + v[:-1]) / 2 * np.diff(t))])
    # Rebase so the lap runs from t=0 to t=lap_duration.
    d0, d1 = np.interp([0, lap.lap_duration], t, dist)
    keep = (t >= 0) & (t <= lap.lap_duration)
    frac = np.concatenate([[0], (dist[keep] - d0) / (d1 - d0), [1]])
    times = np.concatenate([[0], t[keep], [lap.lap_duration]])
    speed = np.interp(times, t, car.speed.to_numpy()[order])
    throttle = np.interp(times, t, car.throttle.to_numpy()[order])
    return pd.DataFrame({"t": times, "frac": frac, "speed": speed, "throttle": throttle})


def zones(ref, lap_m):
    """Split the lap into straight / corner zones from the reference trace."""
    full = (ref.throttle >= FULL_THROTTLE).to_numpy()
    edges = [0.0]
    kinds = [full[0]]
    for i in range(1, len(full)):
        if full[i] != kinds[-1]:
            edges.append((ref.frac.iloc[i - 1] + ref.frac.iloc[i]) / 2)
            kinds.append(full[i])
    edges.append(1.0)
    z = pd.DataFrame({"start": edges[:-1], "end": edges[1:], "straight": kinds})
    # Merge zones shorter than MIN_ZONE_M into the previous zone.
    while True:
        short = z[(z.end - z.start) * lap_m < MIN_ZONE_M]
        if short.empty or len(z) <= 2:
            break
        i = short.index[0]
        j = i - 1 if i > 0 else i + 1
        z.loc[j, ["start", "end"]] = [min(z.start[i], z.start[j]), max(z.end[i], z.end[j])]
        z = z.drop(i).sort_values("start").reset_index(drop=True)
        same = z.straight.eq(z.straight.shift())
        while same.any():  # join neighbouring zones of the same kind
            k = same.idxmax()
            z.loc[k - 1, "end"] = z.end[k]
            z = z.drop(k).reset_index(drop=True)
            same = z.straight.eq(z.straight.shift())
    z["length_m"] = (z.end - z.start) * lap_m
    return z


def measure(tr, z):
    """Time in straight and corner zones, plus corner minimum speeds."""
    t_at = np.interp(np.r_[z.start.to_numpy(), 1.0], tr.frac, tr.t)
    dt = np.diff(t_at)
    mins = [tr.speed[(tr.frac >= s) & (tr.frac <= e)].min()
            for s, e, st in zip(z.start, z.end, z.straight) if not st]
    return {
        "straight_s": dt[z.straight.to_numpy()].sum(),
        "corner_s": dt[~z.straight.to_numpy()].sum(),
        "avg_min_corner_kmh": float(np.nanmean(mins)),
        "top_speed_kmh": float(tr.speed.max()),
    }


def analyse(session_key, lap_km):
    best = fastest_laps(session_key)
    lap_m = lap_km * 1000
    ref_lap = best.iloc[0]
    z = zones(trace(session_key, ref_lap), lap_m)
    rows = []
    for lap in best.itertuples():
        try:
            m = measure(trace(session_key, lap), z)
        except Exception as exc:  # noqa: BLE001 - missing telemetry for one car
            print(f"  skipped {lap.full_name}: {exc}")
            continue
        rows.append({"Driver": lap.full_name.title(), "Team": lap.team_name,
                     "Lap": lap.lap_duration, "Speed trap": lap.st_speed, **m})
    df = pd.DataFrame(rows)
    straight_m = z.length_m[z.straight].sum()
    corner_m = z.length_m[~z.straight].sum()
    df["straight_avg_kmh"] = straight_m / df.straight_s * 3.6
    df["corner_avg_kmh"] = corner_m / df.corner_s * 3.6
    return df, z, ref_lap


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--lap-km", type=float, required=True)
    parser.add_argument("--sessions", nargs="+", default=["Practice 1", "Practice 2"])
    args = parser.parse_args()
    pd.set_option("display.width", 220)
    for s in fetch("sessions", year=args.year, location=args.location):
        if s["session_name"] not in args.sessions:
            continue
        df, z, ref = analyse(s["session_key"], args.lap_km)
        st, co = z[z.straight], z[~z.straight]
        print(f"\n=== {s['session_name']}  (reference: {ref.full_name.title()}, "
              f"{len(st)} straights {st.length_m.sum():.0f} m, "
              f"{len(co)} corner zones {co.length_m.sum():.0f} m)")
        for col, label, asc in (("straight_s", "Straights (time)", True),
                                ("corner_s", "Corners (time)", True),
                                ("top_speed_kmh", "Top speed", False)):
            t = df.sort_values(col, ascending=asc).head(10).reset_index(drop=True)
            print(f"\n{label}")
            print(t[["Driver", "Team", "Lap", "straight_s", "corner_s", "straight_avg_kmh",
                     "corner_avg_kmh", "avg_min_corner_kmh", "top_speed_kmh", "Speed trap"]]
                  .round(3).to_string())


if __name__ == "__main__":
    main()
