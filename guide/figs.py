"""Black-and-white figures for the guide. Run: python figs.py"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

plt.rcParams.update({"font.family": "serif", "font.serif": ["STIXGeneral"], "mathtext.fontset": "stix",
                     "font.size": 9, "svg.fonttype": "path", "axes.linewidth": 0.8})
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")
os.makedirs(OUT, exist_ok=True)


def canvas(w, h, xl, yl):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(*xl)
    ax.set_ylim(*yl)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, t="", fill="white", fs=8.5, ls="-", lw=1, bold=False):
    ax.add_patch(Rectangle((x, y), w, h, fc=fill, ec="black", lw=lw, ls=ls, zorder=2))
    if t:
        ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=fs,
                fontweight="bold" if bold else "normal", zorder=3)


def txt(ax, x, y, t, fs=8.5, ha="center", va="center", style="normal", bold=False):
    ax.text(x, y, t, ha=ha, va=va, fontsize=fs, fontstyle=style,
            fontweight="bold" if bold else "normal", zorder=6)


def arr(ax, p, q, ls="-", lw=1, style="-|>"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=9, lw=lw, ls=ls,
                                 color="black", shrinkA=0, shrinkB=0, zorder=1))


def line(ax, xs, ys, ls="-", lw=1):
    ax.plot(xs, ys, color="black", lw=lw, ls=ls, zorder=1)


def save(fig, n):
    fig.savefig(f"{OUT}/{n}.svg", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


# ---------------------------------------------------------------- 1. system architecture
fig, ax = canvas(7.4, 4.4, (0, 76), (-4, 43))
box(ax, 1, 14, 12, 16, "", fill="#eeeeee")
txt(ax, 7, 26, "RPLIDAR A1", bold=True)
txt(ax, 7, 21, "laser +\nmotor", fs=8)
box(ax, 17, 14, 10, 16, "", ls="--")
txt(ax, 22, 27, "Pmod JE", fs=8, bold=True)
txt(ax, 22, 20.5, "JE1  JE2\nJE3  JE5", fs=7.5)
box(ax, 31, 3, 28, 37, "", ls="--")
txt(ax, 45, 38, "programmable logic (PL)", fs=8, bold=True)
box(ax, 33.5, 27, 23, 7, "AXI UART Lite\n0x42C0_0000", fs=8)
box(ax, 33.5, 16.5, 23, 7, "AXI GPIO\n0x4120_0000", fs=8)
box(ax, 33.5, 6, 23, 7, "motor_pwm.v\n(24 kHz)", fs=8)
box(ax, 63, 3, 12, 37, "", fill="#eeeeee")
txt(ax, 69, 36, "ARM A9 (PS)", fs=8.5, bold=True)
txt(ax, 69, 27, "main.c\nlidar_parse.c\nring buffer", fs=7.5)
txt(ax, 69, 12, "USB-UART\nconsole\nCOM5", fs=7.5)
arr(ax, (13, 28), (17, 28), style="<|-")
txt(ax, 15, 29.8, "TX", fs=7)
arr(ax, (13, 24), (17, 24))
txt(ax, 15, 25.8, "RX", fs=7)
arr(ax, (13, 17), (17, 17), style="<|-")
txt(ax, 15, 15.4, "MOTO", fs=6)
arr(ax, (27, 29.5), (33.5, 29.5), style="<|-")
arr(ax, (27, 24.5), (33.5, 27.5))
line(ax, [33.5, 30, 30], [9.5, 9.5, 16.5])
arr(ax, (30, 16.5), (27, 16.5))
arr(ax, (45, 16.5), (45, 13), style="<|-")
txt(ax, 46.5, 14.8, "duty[7:0]", fs=7, ha="left")
arr(ax, (56.5, 30.5), (63, 30.5), style="<|-|>")
arr(ax, (56.5, 20), (63, 20), style="<|-|>")
txt(ax, 59.7, 32.3, "AXI", fs=7)
arr(ax, (69, 3), (69, -1.5))
txt(ax, 69, -3, "PC: PuTTY / viewer", fs=8)
txt(ax, 45, 1.2, "LD0-LD3 are on GPIO channel 2", fs=7.5, style="italic")
txt(ax, 7, 10, "5 V from a separate\nUSB supply", fs=7.5, style="italic")
save(fig, "arch")

# ---------------------------------------------------------------- 2. packet bits
fig, ax = canvas(7.4, 2.9, (0, 74), (0, 29))
names = [("byte 0", ["Q5", "Q4", "Q3", "Q2", "Q1", "Q0", "S̅", "S"], "quality (6 bits), then S-bar and S"),
         ("byte 1", ["A6", "A5", "A4", "A3", "A2", "A1", "A0", "C"], "angle, low 7 bits, then check bit C (always 1)"),
         ("byte 2", ["A14", "A13", "A12", "A11", "A10", "A9", "A8", "A7"], "angle, high 8 bits"),
         ("byte 3", ["D7", "D6", "D5", "D4", "D3", "D2", "D1", "D0"], "distance, low byte"),
         ("byte 4", ["D15", "D14", "D13", "D12", "D11", "D10", "D9", "D8"], "distance, high byte")]
for r, (nm, bits, desc) in enumerate(names):
    y = 23 - r * 5
    txt(ax, 3, y + 1.8, nm, fs=8, bold=True)
    for i, b in enumerate(bits):
        fill = "#dddddd" if b in ("S̅", "S", "C") else "white"
        box(ax, 7 + i * 4.4, y, 4.4, 3.6, b, fs=7.5, fill=fill)
    txt(ax, 43.5, y + 1.8, desc, fs=8, ha="left")
txt(ax, 7.5, 27.8, "bit 7", fs=7, ha="left")
txt(ax, 7 + 8 * 4.4 - 0.5, 27.8, "bit 0", fs=7, ha="right")
save(fig, "packet")

# ---------------------------------------------------------------- 3. PWM waveforms
fig, axs = plt.subplots(3, 1, figsize=(7.2, 3.1), sharex=True)
T = 4166
thr = {64: 1041, 128: 2083, 192: 3124}
for ax, (d, th) in zip(axs, thr.items()):
    xs, ys = [], []
    for k in range(3):
        xs += [k * T, k * T, k * T + th, k * T + th, (k + 1) * T]
        ys += [0, 1, 1, 0, 0]
    ax.plot(np.array(xs) / 100, ys, color="black", lw=1.2)
    ax.set_yticks([0, 1])
    ax.set_ylim(-0.2, 1.3)
    ax.set_ylabel(f"duty {d}\n({100 * th / T:.0f} %)", fontsize=8, rotation=0, ha="right", va="center")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
axs[-1].set_xlabel("time (µs).  One period = 4166 clocks x 10 ns = 41.7 µs")
fig.tight_layout()
save(fig, "pwm")

# ---------------------------------------------------------------- 4. FIFO overflow
fig, ax = canvas(7.4, 2.8, (0, 74), (0, 28))
txt(ax, 1, 25, "Blocking print (xil_printf)", fs=8.5, ha="left", bold=True)
for i in range(16):
    box(ax, 3 + i * 2.2, 18, 2.2, 3.5, "", fill="#bbbbbb")
txt(ax, 3 + 16 * 2.2 + 1.5, 19.8, "FIFO full after 16 bytes = 1.4 ms,\nthe next byte is LOST", fs=8, ha="left")
arr(ax, (3, 16), (38, 16))
txt(ax, 20, 14.3, "CPU is stuck printing and never reads the FIFO", fs=7.5)
txt(ax, 1, 9.5, "Non-blocking ring buffer (this project)", fs=8.5, ha="left", bold=True)
for i in range(16):
    box(ax, 3 + i * 2.2, 2.5, 2.2, 3.5, "")
txt(ax, 3 + 16 * 2.2 + 1.5, 4.3, "FIFO drained on every loop pass;\nconsole bytes wait in RAM", fs=8, ha="left")
save(fig, "fifo")

# ---------------------------------------------------------------- 5. software data flow
fig, ax = canvas(7.4, 2.4, (0, 74), (0, 24))
steps = [("UART Lite\nRX FIFO", "lidar_getc()"), ("5-byte\nwindow", "lidar_feed()"),
         ("node\n(angle, dist)", "lidar_scan_add()"), ("scan\n(360 bins)", "main loop"),
         ("console\nring buffer", "con_pump()")]
w, gap = 11.5, 4
for i, (t, fn) in enumerate(steps):
    x = 1 + i * (w + gap)
    box(ax, x, 9, w, 9, t, fs=8)
    txt(ax, x + w / 2, 5.5, fn, fs=7.5, style="italic")
    if i < 4:
        arr(ax, (x + w, 13.5), (x + w + gap, 13.5))
txt(ax, 7, 21.5, "raw bytes", fs=8, bold=True)
txt(ax, 7 + (w + gap), 21.5, "bytes to nodes", fs=8, bold=True)
txt(ax, 7 + 2 * (w + gap) + 2, 21.5, "nodes to revolution", fs=8, bold=True)
txt(ax, 7 + 4 * (w + gap) - 1, 21.5, "text to PC", fs=8, bold=True)
save(fig, "flow")

# ---------------------------------------------------------------- 6. bring-up state machine
fig, ax = canvas(7.4, 3.2, (0, 74), (0, 32))
box(ax, 1, 12, 11, 8, "STOP +\nGET_INFO", fs=8)
box(ax, 17, 12, 11, 8, "GET_HEALTH", fs=8)
box(ax, 33, 12, 11, 8, "SCAN +\ndescriptor", fs=8)
box(ax, 49, 12, 11, 8, "streaming\n(LD1 on)", fs=8, bold=True)
for x in (12, 28, 44):
    arr(ax, (x, 16), (x + 5, 16))
txt(ax, 14.5, 17.5, "ok", fs=7)
txt(ax, 30.5, 17.5, "Good", fs=7)
txt(ax, 46.5, 17.5, "0x81", fs=7)
box(ax, 17, 1, 11, 6, "RESET\nwait 1 s", fs=8)
arr(ax, (22.5, 12), (22.5, 7), style="<|-")
txt(ax, 24.5, 9.5, "Error", fs=7, ha="left")
line(ax, [17, 6.5, 6.5], [4, 4, 11.5])
arr(ax, (6.5, 11), (6.5, 12))
line(ax, [54.5, 54.5, 6.5], [20, 28, 28], ls="--")
arr(ax, (6.5, 28), (6.5, 20.5), ls="--")
txt(ax, 30, 29.8, "no bytes for 1.5 s (watchdog): start over", fs=7.5, style="italic")
txt(ax, 36, 9.3, "no answer: wait 1 s and retry", fs=7.5, style="italic")
save(fig, "bringup")

# ---------------------------------------------------------------- 7. duty sweep
duty = [40, 60, 80, 120, 160, 200, 240, 255]
hz = [4.75, 5.18, 5.61, 6.35, 6.92, 7.30, 7.53, 7.53]
pts = [417, 382, 352, 312, 286, 271, 263, 263]
fig, ax = plt.subplots(figsize=(6.4, 3.0))
ax2 = ax.twinx()
ax.plot(duty, hz, "o-", color="black", lw=1.2, ms=4)
ax2.plot(duty, pts, "s--", color="black", lw=1, ms=4, mfc="white")
ax.set_xlabel("PWM duty (0-255)")
ax.set_ylabel("scan rate (Hz), solid")
ax2.set_ylabel("points per revolution, dashed")
ax.axvline(120, color="#888", lw=0.8, ls=":")
ax.text(123, 4.85, "default = 120", fontsize=8)
ax.grid(alpha=0.25)
fig.tight_layout()
save(fig, "sweep")

# ---------------------------------------------------------------- 8. polar sketch
fig = plt.figure(figsize=(3.4, 3.3))
ax = fig.add_subplot(111, projection="polar")
ax.set_theta_zero_location("N")
ax.set_theta_direction(-1)
deg = np.arange(0, 360, 1.15)
th = np.deg2rad(deg)
r = np.full_like(th, 2000.0)
r[(deg > 80) & (deg < 100)] = 600
r[(deg > 340) | (deg < 20)] = 1100
ax.plot(th, r, ".", color="black", ms=2.5)
ax.plot([0], [0], "^", color="black")
ax.set_rmax(2500)
ax.set_rticks([500, 1000, 1500, 2000])
ax.set_yticklabels(["", "1 m", "", "2 m"], fontsize=7)
ax.tick_params(labelsize=7)
ax.set_title("0° = front, angle grows clockwise", fontsize=8)
fig.tight_layout()
save(fig, "polar")
print("figures done")
