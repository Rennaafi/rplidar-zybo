"""Offline checks, no hardware: python selftest.py

1. Python parser vs. the fake lidar (junk bytes, glitches, pure noise)
2. Zybo 'F' frame line decoding used by lidar_view.py --zybo
3. Viewer draws one frame headless (matplotlib Agg) and saves selftest_view.png
"""
import os
import random
import time

import rplidar_proto as rp
from fake_lidar import FakeLidar

errors = 0


def check(cond, msg):
    global errors
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        errors += 1


# 1) fake lidar end to end
lid = FakeLidar(timeout=0.5)
check(rp.get_health(lid) == (0, 0), "health Good")
check(rp.start_scan(lid) == (5, 0x81), "scan descriptor len=5 type=0x81")
parser, revs, got = rp.NodeParser(), rp.RevolutionBuilder(), []
t0 = time.monotonic()
while len(got) < 5 and time.monotonic() - t0 < 5:
    for node in parser.feed(lid.read(lid.in_waiting or 1)):
        r = revs.add(node)
        if r:
            got.append(r)
check(len(got) == 5, f"5 revolutions within 5 s (got {len(got)})")
check(all(340 <= len(r) <= 380 for r in got), f"~364 points per revolution {[len(r) for r in got]}")
s = rp.summarize(got[-1])
check(700 < s["nearest_mm"] < 1000, f"nearest is the box at ~0.8 m ({s['nearest_mm']:.0f} mm)")
rp.stop(lid)

rng = random.Random(3)
p, rb, n_rev = rp.NodeParser(), rp.RevolutionBuilder(), 0
for _ in range(200):
    for node in p.feed(bytes(rng.randrange(256) for _ in range(500))):
        n_rev += rb.add(node) is not None
check(n_rev == 0, f"100 kB of random noise gives no revolutions (got {n_rev})")

# 2) Zybo frame line
import lidar_view  # noqa: E402
bins = [0] * 360
bins[0], bins[90], bins[359] = 1234, 500, 16383
line = "F 551 200 362 330 " + "".join(f"{v:04X}" for v in bins)
f = lidar_view.parse_frame(line)
check(f is not None, "frame line parses")
angles, dists, title = f
check(angles == [0.0, 90.0, 359.0] and dists == [1234.0, 500.0, 16383.0], "frame bins decoded")
check("5.51 Hz" in title and "500 mm @ 90" in title, f"frame title: {title}")
check(lidar_view.parse_frame("F 1 2 3 4 ABC") is None, "short frame rejected")

# 3) headless render
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import math  # noqa: E402
ax = plt.figure(figsize=(6, 6)).add_subplot(projection="polar")
ax.set_theta_zero_location("N")
ax.set_theta_direction(-1)
ax.set_rmax(4000)
valid = [n for n in got[-1] if n[3] > 0]
ax.scatter([math.radians(n[2]) for n in valid], [n[3] for n in valid], s=6,
           c=[n[3] for n in valid], cmap="viridis_r", vmin=0, vmax=4000)
ax.set_title("selftest: fake room + box")
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selftest_view.png")
plt.savefig(out, dpi=80)
check(os.path.getsize(out) > 5000, f"rendered {out}")

print("ALL TESTS PASSED" if errors == 0 else f"{errors} TEST(S) FAILED")
raise SystemExit(errors != 0)
