"""Instagram / YouTube Shorts graphics: Rohit Sharma in ODIs vs New Zealand.

Same design and carousel as social_graphics_kohli_nz.py, with reel slides written
for Rohit's story. Saves to cricket/output/social_rohit/.

    python cricket/social_graphics_rohit_nz.py
"""

import social_graphics_kohli_nz as g
from social_graphics_kohli_nz import (ACCENT, INK, INK_2, MUTED, bdry_line, canvas, footer,
                                      kicker, panel, save, stat_block, text)

g.OUT = g.HERE / "output" / "social_rohit"


def reel_slides(s):
    b, vs, home, car = s["bowlers"], s["vs_nz"], s["nz_home"], s["career"]

    fig = canvas(1920)
    kicker(fig, 0.80, "Rohit Sharma in ODIs")
    text(fig, 0.5, 0.645, f"{home['100s']} HUNDREDS", 104, ACCENT, "bold")
    text(fig, 0.5, 0.56, "IN NEW ZEALAND", 84, INK, "bold")
    text(fig, 0.5, 0.42, f"{home['innings']} innings. Best score: {home['hs']}.\n"
         "New Zealand keeps testing him", 44, INK_2, linespacing=1.4)
    footer(fig, s["data_to"])
    save(fig, "reel_01_hook.png")

    fig = canvas(1920)
    kicker(fig, 0.80, "vs New Zealand · all venues")
    text(fig, 0.5, 0.735, "Below his best", 56, INK, "bold")
    stat_block(fig, 0.27, 0.60, f"{vs['avg']:.1f}", "average vs NZ", 96)
    stat_block(fig, 0.73, 0.60, f"{car['avg']:.1f}", "career average", 96)
    text(fig, 0.5, 0.44, f"{vs['runs']:,} runs  ·  {vs['100s']} hundreds  ·  HS {vs['hs']}", 38, INK_2)
    text(fig, 0.5, 0.33, f"{vs['matches']} ODIs  ·  SR {vs['sr']:.1f}  ·  dots {vs['dot']:.1f}%",
         34, INK_2)
    text(fig, 0.5, 0.28, f"Boundary %: {vs['bdry']:.1f}%  ·  career {car['bdry']:.1f}%", 34, INK_2)
    footer(fig, s["data_to"])
    save(fig, "reel_02_vs_nz.png")

    fig = canvas(1920)
    kicker(fig, 0.80, "In New Zealand")
    text(fig, 0.5, 0.735, "The brakes come on", 56, INK, "bold")
    stat_block(fig, 0.27, 0.60, f"{home['sr']:.1f}", "strike rate", 96)
    stat_block(fig, 0.73, 0.60, f"{home['avg']:.1f}", "average", 96)
    stat_block(fig, 0.5, 0.43, f"{home['dot']:.1f}%", "of balls are dots")
    text(fig, 0.5, 0.31, f"Career: SR {car['sr']:.1f}  ·  average {car['avg']:.1f}  ·  "
         f"dots {car['dot']:.1f}%", 32, MUTED)
    text(fig, 0.5, 0.26, f"Boundary %: {home['bdry']:.1f}%  ·  career {car['bdry']:.1f}%",
         34, INK_2)
    footer(fig, s["data_to"])
    save(fig, "reel_03_in_nz.png")

    j = b["Kyle Jamieson"]
    fig = canvas(1920)
    kicker(fig, 0.80, "vs Kyle Jamieson")
    text(fig, 0.5, 0.71, "3 in every 4 balls: dots", 56, INK, "bold")
    stat_block(fig, 0.5, 0.56, f"{j['dot']:.1f}%", "dot balls", 150)
    text(fig, 0.5, 0.40, f"{j['runs']} runs off {j['balls']} balls\n"
         f"SR {j['sr']:.1f}  ·  out {j['outs']} times", 38, INK_2, linespacing=1.5)
    bdry_line(fig, j, car)
    footer(fig, s["data_to"])
    save(fig, "reel_04_jamieson.png")

    h, f = b["Matt Henry"], b["Lockie Ferguson"]
    fig = canvas(1920)
    kicker(fig, 0.80, "Henry & Ferguson")
    text(fig, 0.5, 0.735, "Pace keeps him quiet", 56, INK, "bold")
    for x, name, d in ((0.27, "Matt Henry", h), (0.73, "Lockie Ferguson", f)):
        panel(fig, x - 0.21, 0.345, 0.42, 0.335)
        text(fig, x, 0.635, name, 34, INK, "bold")
        text(fig, x, 0.555, f"{d['dot']:.0f}%", 110, ACCENT, "bold")
        text(fig, x, 0.495, "dot balls", 28, INK_2)
        text(fig, x, 0.425, f"{d['runs']} off {d['balls']}  ·  out {d['outs']}", 28, INK_2)
        text(fig, x, 0.38, f"Boundary %: {d['bdry_pct']:.1f}%", 28, INK_2)
    text(fig, 0.5, 0.285, f"Rohit's career: {car['dot']:.1f}% dots  ·  {car['bdry']:.1f}% boundaries",
         30, MUTED)
    footer(fig, s["data_to"])
    save(fig, "reel_05_henry_ferguson.png")

    sant = b["Mitchell Santner"]
    fig = canvas(1920)
    kicker(fig, 0.80, "vs Mitchell Santner")
    text(fig, 0.5, 0.71, "Spin? No problem", 56, INK, "bold")
    stat_block(fig, 0.5, 0.56, f"{sant['avg']:.1f}", "average", 170)
    text(fig, 0.5, 0.40, f"{sant['runs']} runs off {sant['balls']} balls\n"
         f"SR {sant['sr']:.1f}  ·  out {sant['outs']} times", 38, INK_2, linespacing=1.5)
    bdry_line(fig, sant, car)
    footer(fig, s["data_to"])
    save(fig, "reel_06_santner.png")

    d, c = b["Jacob Duffy"], b["Kristian Clarke"]
    fig = canvas(1920)
    kicker(fig, 0.82, "The new faces")
    text(fig, 0.5, 0.715, "WHO WINS\nNEXT TIME?", 90, INK, "bold", linespacing=1.1)
    for x, name, v, big in ((0.27, "Jacob Duffy", d, f"{d['runs']} off {d['balls']}"),
                            (0.73, "Kristian Clarke", c, f"{c['outs']} out")):
        panel(fig, x - 0.21, 0.37, 0.42, 0.23)
        text(fig, x, 0.565, name, 34, INK, "bold")
        text(fig, x, 0.495, big, 64, ACCENT, "bold")
        sub = (f"not out yet  ·  SR {v['sr']:.0f}" if v["outs"] == 0
               else f"in {v['balls']} balls")
        text(fig, x, 0.435, sub, 28, INK_2)
        text(fig, x, 0.395, f"Boundary %: {v['bdry_pct']:.1f}%", 28, INK_2)
    text(fig, 0.5, 0.30, "Comment below", 48, ACCENT, "bold")
    footer(fig, s["data_to"])
    save(fig, "reel_07_question.png")


def main():
    s = g.compute("RG Sharma", "Rohit")
    reel_slides(s)
    g.carousel_slides(s)
    print("Saved", len(list(g.OUT.glob("*.png"))), "images to", g.OUT)


if __name__ == "__main__":
    main()
