"""Instagram Reel frames (1080x1920) for the Mexico City GP 2026 voiceover.

Fits the existing 4:5 graphics into the reel's safe zone (clear of the app's top bar
and bottom caption area) and adds a title/podium card and an end card. Run
sector_graphics.py and track_dominance.py first; frames go to f1/output/reel/.

    python f1/reel_graphics.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
from PIL import Image  # noqa: E402

from track_dominance import BG, DRIVER_COLOURS, INK, INK_2, MUTED  # noqa: E402

HERE = Path(__file__).resolve().parent
SRC = HERE / "output"
OUT = SRC / "reel"
W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = int(H * 0.15), int(H * 0.80)  # keep content between these
ACCENT = "#FFB000"
plt.rcParams["font.family"] = "Liberation Sans"


def fit_into_reel(src, dst):
    """Scale a graphic into the reel's safe zone on the dark background."""
    im = Image.open(src).convert("RGB")
    scale = min(W / im.width, (SAFE_BOTTOM - SAFE_TOP) / im.height)
    im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    frame = Image.new("RGB", (W, H), BG)
    frame.paste(im, ((W - im.width) // 2, SAFE_TOP))
    frame.save(dst)


def text(fig, x, y, s, size, color=INK, weight="normal", **kw):
    fig.text(x, y, s, fontsize=size, color=color, fontweight=weight, ha="center",
             va="center", **kw)


def title_card(dst):
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor(BG)
    text(fig, 0.5, 0.80, "MEXICO CITY GP 2026", 30, ACCENT, "bold")
    text(fig, 0.5, 0.735, "KIMI ANTONELLI", 66, INK, "bold")
    text(fig, 0.5, 0.685, "Youngest Formula 1 World Champion", 36, INK_2)
    text(fig, 0.5, 0.648, "Title sealed with four races to go", 26, MUTED)
    # Podium blocks: P2 left, P1 centre, P3 right.
    podium = [("P2", "Lewis Hamilton", "HAM", "+0.799s", 0.20, 0.15),
              ("P1", "Max Verstappen", "VER", "Winner", 0.50, 0.21),
              ("P3", "Kimi Antonelli", "ANT", "Champion", 0.80, 0.11)]
    base = 0.30
    for pos, name, code, note, x, h in podium:
        fig.patches.append(FancyBboxPatch(
            (x - 0.135, base), 0.27, h, boxstyle="round,pad=0,rounding_size=0.012",
            transform=fig.transFigure, facecolor=DRIVER_COLOURS[code], edgecolor="none"))
        text(fig, x, base + h - 0.035, pos, 44, INK, "bold")
        text(fig, x, base + h + 0.05, name.split()[0], 26, INK_2)
        text(fig, x, base + h + 0.022, name.split()[-1].upper(), 32, INK, "bold")
        text(fig, x, base + 0.03, note, 22, INK, "bold")
    text(fig, 0.5, 0.235, "Data: OpenF1", 20, MUTED)
    fig.savefig(dst, facecolor=BG)
    plt.close(fig)


def end_card(dst):
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor(BG)
    text(fig, 0.5, 0.66, "WHO IMPRESSED\nYOU MOST\nIN MEXICO?", 76, INK, "bold",
         linespacing=1.15)
    text(fig, 0.5, 0.49, "Tell me in the comments", 38, ACCENT, "bold")
    text(fig, 0.5, 0.40, "Follow for more F1 data stories", 32, INK_2)
    text(fig, 0.5, 0.235, "Data: OpenF1 timing & telemetry", 20, MUTED)
    fig.savefig(dst, facecolor=BG)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stem = "2026_mexico_city"
    frames = [
        ("01_title_podium.png", None),
        ("02_q3_fastest_sectors.png", f"{stem}_sectors_q3.png"),
        ("03_race_average_sectors.png", f"{stem}_sectors_race_avg.png"),
        ("04_q3_corners_straights.png",
         f"{stem}_q3_track_dominance_speed_only_ver_ham_ant_lec_rus_nor.png"),
        ("05_race_corners_straights.png",
         f"{stem}_race_track_dominance_avg_speed_only_ver_ham_ant_lec_rus_nor.png"),
        ("06_end_card.png", None),
    ]
    for name, src in frames:
        dst = OUT / name
        if src:
            fit_into_reel(SRC / src, dst)
        elif "title" in name:
            title_card(dst)
        else:
            end_card(dst)
        print("Saved", dst)


if __name__ == "__main__":
    main()
