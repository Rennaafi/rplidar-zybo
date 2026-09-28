"""Raw wiring diagnosis for the lidar on a USB-TTL adapter.

  python rplidar_sniff.py COM13            # listen + poke the lidar
  python rplidar_sniff.py COM13 --loop     # test the adapter alone (TXD wired to RXD)

Step 1 only LISTENS for 10 s. Unplug the lidar's 5 V and plug it back in
during that time: an RPLIDAR prints a short text banner when it boots, so any
bytes here prove lidar TX -> adapter RXD works, even if our commands can't
reach the lidar.
Step 2 sends RESET / GET_HEALTH / GET_INFO at 115200 and prints every byte
that comes back (hex + text).
"""
import argparse
import sys
import time

import rplidar_proto


def dump(tag, data):
    if not data:
        print(f"  {tag}: nothing")
        return
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    print(f"  {tag}: {len(data)} bytes")
    for i in range(0, min(len(data), 96), 16):
        chunk = data[i:i + 16]
        print("    " + " ".join(f"{b:02X}" for b in chunk).ljust(48) + "  " + text[i:i + 16])


def listen(ser, seconds):
    end, buf = time.monotonic() + seconds, bytearray()
    while time.monotonic() < end:
        buf += ser.read(ser.in_waiting or 1)
    return bytes(buf)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port")
    ap.add_argument("--loop", action="store_true", help="adapter self-test, TXD jumpered to RXD")
    args = ap.parse_args()

    try:
        ser = rplidar_proto.open_lidar_port(args.port, timeout=0.1)
    except Exception as e:
        sys.exit(f"Cannot open {args.port}: {e}")

    if args.loop:
        ser.reset_input_buffer()
        ser.write(b"HELLO-LOOPBACK")
        got = listen(ser, 0.5)
        dump("loopback", got)
        print("ADAPTER OK" if got == b"HELLO-LOOPBACK" else "ADAPTER PROBLEM: TXD->RXD jumper not seen")
        return

    print("STEP 1: listening 10 s. Unplug the lidar's 5 V now and plug it back in...")
    dump("boot banner", listen(ser, 10))

    print("STEP 2: poking the lidar at 115200")
    for name, cmd, wait in (("STOP", 0x25, 0.1), ("RESET", 0x40, 1.0),
                            ("GET_HEALTH", 0x52, 0.5), ("GET_INFO", 0x50, 0.5)):
        ser.reset_input_buffer()
        ser.write(bytes([0xA5, cmd]))
        dump(name, listen(ser, wait))
    ser.close()

    print("\nHow to read this:")
    print("  bytes in STEP 1 or after RESET -> lidar TX reaches the adapter")
    print("  A5 5A ... after GET_HEALTH     -> both directions work")
    print("  nothing anywhere               -> lidar TX isn't reaching RXD (wire/contact/pin)")


if __name__ == "__main__":
    main()
