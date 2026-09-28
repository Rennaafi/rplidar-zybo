"""Stage 1 bench test: RPLIDAR A1 -> USB-TTL (3.3 V) -> laptop.

  python rplidar_test.py COM5          # real lidar
  python rplidar_test.py --fake        # software lidar, no hardware needed

Prints device info, health, the scan descriptor, then one line per revolution.
Ctrl+C to stop (sends STOP so the lidar goes idle).
"""
import argparse
import sys
import time

import rplidar_proto as rp


def open_port(args):
    if args.fake:
        from fake_lidar import FakeLidar
        return FakeLidar(timeout=1)
    return rp.open_lidar_port(args.port, timeout=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", nargs="?", default="COM5", help="serial port, e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("--fake", action="store_true", help="use the software lidar")
    ap.add_argument("--revs", type=int, default=0, help="stop after N revolutions (0 = run forever)")
    args = ap.parse_args()

    try:
        ser = open_port(args)
    except Exception as e:
        sys.exit(f"Cannot open {args.port}: {e}\n(Device Manager -> Ports (COM & LPT) shows the right name)")

    try:
        info = rp.get_info(ser)
        print(f"Model {info['model']} FW {info['firmware']} HW {info['hardware']} SN {info['serial']}")

        status, err = rp.get_health(ser)
        name = rp.HEALTH_NAMES[status] if status < 3 else "?"
        print(f"Health: {name}  error code: {err}")
        if status == 2:
            print("Health = Error -> sending RESET, power-cycle the lidar if it persists")
            rp.send(ser, rp.CMD_RESET)
            time.sleep(1)
            sys.exit(1)

        n, t = rp.start_scan(ser)
        ok = "(ok)" if (n, t) == (5, 0x81) else "(UNEXPECTED, expected len=5 type=0x81)"
        print(f"Scan descriptor: len={n} type=0x{t:02X} {ok}")

        parser, revs = rp.NodeParser(), rp.RevolutionBuilder()
        t_last, count = None, 0
        while True:
            data = ser.read(ser.in_waiting or 1)
            for node in parser.feed(data):
                rev = revs.add(node)
                if rev is None:
                    continue
                now = time.monotonic()
                hz = 1.0 / (now - t_last) if t_last else 0.0
                t_last = now
                s = rp.summarize(rev)
                print(f"{s['points']:4d} pts, {s['valid']:4d} valid | {hz:4.1f} Hz | "
                      f"front: {s['front_mm']:7.1f} mm | "
                      f"nearest: {s['nearest_mm']:7.1f} mm @ {s['nearest_deg']:6.1f} deg")
                count += 1
                if args.revs and count >= args.revs:
                    return
    except KeyboardInterrupt:
        pass
    except TimeoutError as e:
        print("ERROR:", e)
        sys.exit(1)
    finally:
        rp.send(ser, rp.CMD_STOP)
        time.sleep(0.05)
        ser.close()


if __name__ == "__main__":
    main()
