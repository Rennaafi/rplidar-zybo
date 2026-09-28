"""Live polar plot of the lidar scan.

  python lidar_view.py --lidar COM5    # Stage 1: lidar on the USB-TTL adapter
  python lidar_view.py --zybo COM7     # Stage 2B: Zybo console port (app streams 'F' frames)
  python lidar_view.py --fake          # software lidar, no hardware needed

Keys in the plot window (Zybo mode): + / - motor duty, m motor on/off, r restart scan.
Close the window or Ctrl+C to quit.
"""
import argparse
import math
import sys
import threading
import time

import rplidar_proto as rp


class Latest:
    """Most recent revolution, shared between the reader thread and the plot."""

    def __init__(self):
        self.lock = threading.Lock()
        self.angles = []   # degrees
        self.dists = []    # mm
        self.title = "waiting for data..."
        self.error = None

    def set(self, angles, dists, title):
        with self.lock:
            self.angles, self.dists, self.title = angles, dists, title


def lidar_reader(ser, latest, stop_evt):
    """Talk to the lidar directly (Stage 1 or --fake)."""
    try:
        info = rp.get_info(ser)
        status, _ = rp.get_health(ser)
        print(f"Model {info['model']} FW {info['firmware']}  health {rp.HEALTH_NAMES[min(status, 2)]}")
        print("Scan descriptor: len=%d type=0x%02X" % rp.start_scan(ser))
        parser, revs = rp.NodeParser(), rp.RevolutionBuilder()
        t_last = None
        while not stop_evt.is_set():
            for node in parser.feed(ser.read(ser.in_waiting or 1)):
                rev = revs.add(node)
                if rev is None:
                    continue
                now = time.monotonic()
                hz = 1.0 / (now - t_last) if t_last else 0.0
                t_last = now
                s = rp.summarize(rev)
                valid = [p for p in rev if p[3] > 0]
                latest.set([p[2] for p in valid], [p[3] for p in valid],
                           f"{hz:4.1f} Hz  {s['valid']}/{s['points']} pts  "
                           f"nearest {s['nearest_mm']:.0f} mm @ {s['nearest_deg']:.0f} deg")
    except Exception as e:
        latest.error = str(e)
    finally:
        rp.send(ser, rp.CMD_STOP)


def parse_frame(line):
    """'F <hz_x100> <duty> <points> <valid> <1440 hex>' -> (angles, dists, title) or None."""
    parts = line.split()
    if len(parts) != 6 or parts[0] != "F" or len(parts[5]) != 360 * 4:
        return None
    hz, duty, pts, valid = (int(x) for x in parts[1:5])
    hexs = parts[5]
    angles, dists = [], []
    for deg in range(360):
        mm = int(hexs[deg * 4:deg * 4 + 4], 16)
        if mm:
            angles.append(float(deg))
            dists.append(float(mm))
    near = min(zip(dists, angles), default=(0, 0))
    title = (f"Zybo: {hz / 100:4.2f} Hz  duty {duty}  {valid}/{pts} pts  "
             f"nearest {near[0]:.0f} mm @ {near[1]:.0f} deg")
    return angles, dists, title


def zybo_reader(ser, latest, stop_evt):
    """Read the Zybo console: 'F' frames go to the plot, everything else is printed."""
    ser.write(b"F")   # frames on
    buf = b""
    try:
        while not stop_evt.is_set():
            buf += ser.read(ser.in_waiting or 1)
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("ascii", "replace").strip()
                if line.startswith("F "):
                    f = parse_frame(line)
                    if f:
                        latest.set(*f)
                elif line:
                    print(line)
    except Exception as e:
        latest.error = str(e)
    finally:
        try:
            ser.write(b"x")   # frames off, console is readable again in PuTTY
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--lidar", metavar="PORT", help="lidar on a USB-TTL adapter")
    src.add_argument("--zybo", metavar="PORT", help="Zybo USB-UART console port")
    src.add_argument("--fake", action="store_true", help="software lidar")
    ap.add_argument("--range", type=float, default=4000, help="plot radius in mm (default 4000)")
    args = ap.parse_args()

    try:
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation
    except ImportError:
        sys.exit("matplotlib missing: pip install -r requirements.txt")

    if args.fake:
        from fake_lidar import FakeLidar
        ser, reader = FakeLidar(timeout=0.2), lidar_reader
    else:
        import serial
        port = args.lidar or args.zybo
        try:
            ser = (rp.open_lidar_port(port, timeout=0.2) if args.lidar
                   else serial.Serial(port, 115200, timeout=0.2))
        except Exception as e:
            sys.exit(f"Cannot open {port}: {e}")
        reader = lidar_reader if args.lidar else zybo_reader

    latest, stop_evt = Latest(), threading.Event()
    th = threading.Thread(target=reader, args=(ser, latest, stop_evt), daemon=True)
    th.start()

    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(projection="polar")
    ax.set_theta_zero_location("N")   # 0 deg = lidar front, pointing up
    ax.set_theta_direction(-1)        # RPLIDAR angles grow clockwise
    ax.set_rmax(args.range)
    ax.set_rlabel_position(135)
    sc = ax.scatter([], [], s=6, c=[], cmap="viridis_r", vmin=0, vmax=args.range)
    ax.plot([0], [0], marker="^", color="red", markersize=10)
    title = ax.set_title("waiting for data...")

    def update(_):
        if latest.error:
            title.set_text("ERROR: " + latest.error)
            return sc, title
        with latest.lock:
            th_, r_, t_ = latest.angles, latest.dists, latest.title
        if th_:
            sc.set_offsets(list(zip([math.radians(a) for a in th_], r_)))
            sc.set_array(r_)
        title.set_text(t_)
        return sc, title

    def on_key(ev):
        if args.zybo and ev.key in ("+", "-", "m", "r"):
            ser.write(ev.key.encode())

    fig.canvas.mpl_connect("key_press_event", on_key)
    anim = FuncAnimation(fig, update, interval=100, cache_frame_data=False)  # noqa: F841 (keep ref)
    try:
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        th.join(timeout=1)
        ser.close()


if __name__ == "__main__":
    main()
