"""Hand-traced circuit outlines for track maps (no position data needed).

Each circuit is a list of (x, y) waypoints in driving order, starting and ending at
the start/finish line, traced from the official circuit map in image pixels
(y grows downwards). `anchors` are waypoint indices where sections change, in lap
order: the boundaries between straights and corner sections that
straights_vs_corners.zones() finds. Pinning boundaries to corners keeps each
section on the right part of the drawing even though the map isn't to scale.
"""

import numpy as np

CIRCUITS = {
    # Autódromo Hermanos Rodríguez, traced from the F1 circuit map (392x220 px).
    "Mexico City": {
        "points": [
            (80, 17), (150, 18), (250, 19), (322, 20),             # 0-3  main straight
            (336, 22), (338, 34), (342, 39), (349, 42), (350, 52),  # 4-8  Turns 1-3
            (340, 90), (320, 135), (303, 168),                     # 9-11 back straight
            (297, 178), (306, 186), (296, 195), (287, 205),        # 12-15 Turns 4-6
            (283, 200), (284, 190),                                # 16-17
            (284, 160), (284, 142),                                # 18-19 straight to T7
            (280, 134), (270, 127), (261, 120), (257, 110),        # 20-23 Esses
            (250, 107), (230, 108), (210, 109), (205, 99),
            (200, 88),                                             # 28
            (180, 79), (150, 74), (100, 74),                       # 29-31 straight to T12
            (84, 73), (80, 55), (77, 40), (73, 38), (69, 44),      # 32-36 Stadium
            (66, 48), (58, 48), (45, 47), (41, 40), (43, 28),
            (50, 20), (62, 17),                                    # 42-43 exit of T17
            (80, 17),                                              # 44  finish line
        ],
        # main straight | T1-3 | back straight | T4-6 | to T7 | Esses | to T12 | Stadium | main
        "anchors": [3, 8, 11, 17, 19, 28, 31, 43],
        "sections": ["Main straight", "Turns 1-3", "Back straight", "Turns 4-6",
                     "Straight to T7", "Esses (T7-11)", "Straight to T12", "Stadium (T12-17)"],
        # Fixed label spots (image px) where the automatic placement is cramped.
        "labels": {4: (262, 168), 7: (32, 66)},
    },
}


def traced_outline(name, zone_starts, last_zone_end, step=1.0):
    """Densified (frac, xy) for a traced circuit.

    zone_starts: start fraction of each section (the lap's final main-straight part
    already merged into the first section); last_zone_end: where the last corner
    section ends. Points between two anchors are spread evenly by length over that
    section's share of the lap.
    """
    c = CIRCUITS[name]
    pts = np.array(c["points"], dtype=float)
    pts[:, 1] *= -1  # image y grows downwards
    idx = [0] + c["anchors"] + [len(pts) - 1]
    fr = list(zone_starts) + [last_zone_end, 1.0]
    if len(fr) != len(idx):
        raise ValueError(f"{name}: {len(c['anchors'])} anchors for {len(zone_starts)} sections")
    frs, xys = [], []
    for k in range(len(idx) - 1):
        seg = pts[idx[k]:idx[k + 1] + 1]
        lens = np.r_[0, np.cumsum(np.linalg.norm(np.diff(seg, axis=0), axis=1))]
        s = np.linspace(0, lens[-1], max(int(lens[-1] / step), 2), endpoint=False)
        frs.append(fr[k] + (fr[k + 1] - fr[k]) * s / lens[-1])
        xys.append(np.column_stack([np.interp(s, lens, seg[:, 0]), np.interp(s, lens, seg[:, 1])]))
    return np.concatenate(frs), np.vstack(xys)


def label_positions(name):
    """Fixed label spots for a traced circuit, in plot coordinates (y flipped)."""
    return {k: (x, -y) for k, (x, y) in CIRCUITS[name].get("labels", {}).items()}
