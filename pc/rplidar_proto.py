"""RPLIDAR A1 raw serial protocol (same logic as sw/src/lidar_parse.c).

Works with anything that looks like a pyserial port: a real serial.Serial or
fake_lidar.FakeLidar.
"""
import time

CMD_STOP = 0x25
CMD_RESET = 0x40
CMD_SCAN = 0x20
CMD_GET_INFO = 0x50
CMD_GET_HEALTH = 0x52

HEALTH_NAMES = ["Good", "Warning", "Error"]

LOCK_NODES = 3        # consecutive good nodes before trusting alignment
MIN_REV_POINTS = 100  # shorter "revolutions" are sync glitches


def open_lidar_port(port, timeout=1.0):
    """Open a lidar serial port with DTR released.

    The official RoboPeak/Slamtec USB adapter drives MOTOCTL from DTR, and the
    motor only spins with DTR released (the Slamtec SDK does the same). On a
    plain CP2102 the DTR pin is unused, so this is harmless there.
    """
    import serial
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = timeout
    ser.dtr = False
    ser.open()
    return ser


def send(ser, cmd):
    ser.write(bytes([0xA5, cmd]))


def read_descriptor(ser):
    """Wait for A5 5A + 5 bytes. Returns (length, data_type)."""
    while True:
        b = ser.read(1)
        if not b:
            raise TimeoutError("Timeout waiting for response descriptor "
                               "(check TX/RX crossed, GND, 5 V, port name)")
        if b[0] == 0xA5:
            b2 = ser.read(1)
            if b2 == b"\x5A":
                break
    d = ser.read(5)
    if len(d) != 5:
        raise TimeoutError("Truncated response descriptor")
    length = d[0] | (d[1] << 8) | (d[2] << 16) | ((d[3] & 0x3F) << 24)
    return length, d[4]


def stop(ser):
    send(ser, CMD_STOP)
    time.sleep(0.05)
    ser.reset_input_buffer()


def get_info(ser):
    stop(ser)
    send(ser, CMD_GET_INFO)
    n, _ = read_descriptor(ser)
    info = ser.read(n)
    if len(info) < 20:
        raise TimeoutError("Short GET_INFO payload")
    return {
        "model": info[0],
        "firmware": f"{info[2]}.{info[1]:02d}",
        "hardware": info[3],
        "serial": info[4:20].hex().upper(),
    }


def get_health(ser):
    stop(ser)
    send(ser, CMD_GET_HEALTH)
    n, _ = read_descriptor(ser)
    h = ser.read(n)
    if len(h) < 3:
        raise TimeoutError("Short GET_HEALTH payload")
    return h[0], h[1] | (h[2] << 8)


def start_scan(ser):
    send(ser, CMD_SCAN)
    return read_descriptor(ser)   # expect (5, 0x81)


class NodeParser:
    """Bytes in, (start, quality, angle_deg, dist_mm) nodes out."""

    def __init__(self):
        self.buf = bytearray()
        self.good_run = 0
        self.resync_drops = 0

    def feed(self, data):
        self.buf += data
        buf = self.buf
        i = 0
        out = []
        while len(buf) - i >= 5:
            b0, b1, b2 = buf[i], buf[i + 1], buf[i + 2]
            s, s_inv, c = b0 & 1, (b0 >> 1) & 1, b1 & 1
            ang_q6 = (b2 << 7) | (b1 >> 1)
            if s == s_inv or c != 1 or ang_q6 >= 360 * 64:
                i += 1
                self.resync_drops += 1
                self.good_run = 0
                continue
            dist_q2 = buf[i + 3] | (buf[i + 4] << 8)
            i += 5
            if self.good_run < LOCK_NODES:
                self.good_run += 1
                if self.good_run < LOCK_NODES:
                    continue
            out.append((s, b0 >> 2, ang_q6 / 64.0, dist_q2 / 4.0))
        del buf[:i]
        return out


class RevolutionBuilder:
    """Groups nodes into revolutions using the S (start) bit."""

    def __init__(self):
        self.cur = []
        self.seen_start = False

    def add(self, node):
        """Returns the finished revolution (list of nodes) or None."""
        done = None
        if node[0]:
            if self.seen_start and len(self.cur) >= MIN_REV_POINTS:
                done = self.cur
            self.seen_start = True
            self.cur = []
        self.cur.append(node)
        return done


def summarize(rev):
    valid = [p for p in rev if p[3] > 0]
    front = min((p for p in valid if min(p[2], 360 - p[2]) <= 30),
                key=lambda p: p[3], default=None)
    near = min(valid, key=lambda p: p[3], default=None)
    return {
        "points": len(rev),
        "valid": len(valid),
        "front_mm": front[3] if front else 0.0,
        "nearest_mm": near[3] if near else 0.0,
        "nearest_deg": near[2] if near else 0.0,
    }
