"""Software RPLIDAR A1 that behaves like a pyserial port.

Lets you run rplidar_test.py / lidar_view.py with --fake before the real
hardware is wired. It answers GET_INFO / GET_HEALTH / SCAN / STOP and streams
~2000 nodes/s at ~5.5 Hz, room 4 m x 3 m with a box that moves around.
"""
import math
import random
import threading
import time


class FakeLidar:
    SAMPLES_PER_SEC = 2000
    REV_HZ = 5.5

    def __init__(self, timeout=1.0, noise_bytes=True):
        self.timeout = timeout
        self._rx = bytearray()
        self._lock = threading.Lock()
        self._scanning = False
        self._t_scan = 0.0
        self._sent = 0
        self._noise = noise_bytes
        self._rng = random.Random(1)
        self.is_open = True

    # ---- pyserial-like API
    def write(self, data):
        data = bytes(data)
        for i in range(len(data) - 1):
            if data[i] == 0xA5:
                self._command(data[i + 1])
        return len(data)

    @property
    def in_waiting(self):
        self._generate()
        return len(self._rx)

    def read(self, n=1):
        deadline = time.monotonic() + (self.timeout or 0)
        while True:
            self._generate()
            with self._lock:
                if len(self._rx) >= n or time.monotonic() >= deadline:
                    out = bytes(self._rx[:n])
                    del self._rx[:n]
                    return out
            time.sleep(0.002)

    def reset_input_buffer(self):
        with self._lock:
            self._rx.clear()

    def close(self):
        self.is_open = False

    # ---- device behaviour
    def _push(self, data):
        with self._lock:
            self._rx += data

    def _command(self, cmd):
        if cmd == 0x25:            # STOP
            self._scanning = False
        elif cmd == 0x50:          # GET_INFO
            self._push(bytes([0xA5, 0x5A, 0x14, 0, 0, 0, 0x04]))
            self._push(bytes([24, 29, 1, 0]) + bytes.fromhex("FA4E9AF0C9E09ED2A0EA98F34B6E3A1C"))
        elif cmd == 0x52:          # GET_HEALTH
            self._push(bytes([0xA5, 0x5A, 0x03, 0, 0, 0, 0x06, 0, 0, 0]))
        elif cmd in (0x20, 0x21):  # SCAN
            self._push(bytes([0xA5, 0x5A, 0x05, 0, 0, 0x40, 0x81]))
            self._scanning = True
            self._t_scan = time.monotonic()
            self._sent = 0

    def _distance(self, deg, t):
        a = math.radians(deg)
        # clockwise angles, 0 deg = +y (front); x to the right
        dx, dy = math.sin(a), math.cos(a)
        best = None
        for (wall, lim) in ((2.0, dx), (-2.0, dx), (1.8, dy), (-1.2, dy)):
            if lim != 0:
                k = wall / lim
                if k > 0 and (best is None or k < best):
                    best = k
        # a 0.4 m box circling at 1.0 m
        bx, by = 1.0 * math.sin(t * 0.6), 1.0 * math.cos(t * 0.6)
        proj = bx * dx + by * dy
        if proj > 0:
            perp = abs(bx * dy - by * dx)
            if perp < 0.2:
                k = proj - math.sqrt(0.04 - perp * perp)
                best = min(best, k) if best else k
        mm = (best or 0) * 1000
        if mm > 6000 or self._rng.random() < 0.08:
            return 0.0
        return mm + self._rng.gauss(0, 4)

    def _generate(self):
        if not self._scanning:
            return
        now = time.monotonic() - self._t_scan
        target = int(now * self.SAMPLES_PER_SEC)
        per_rev = self.SAMPLES_PER_SEC / self.REV_HZ
        out = bytearray()
        while self._sent < target:
            i = self._sent
            pos = (i % per_rev) / per_rev
            start = 1 if (i % per_rev) < 1 else 0
            deg = pos * 360.0
            mm = self._distance(deg, i / self.SAMPLES_PER_SEC)
            a = int(deg * 64) % (360 * 64)
            d = int(mm * 4) & 0xFFFF
            q = 0 if d == 0 else 47
            out += bytes([(q << 2) | ((1 - start) << 1) | start,
                          ((a & 0x7F) << 1) | 1, a >> 7, d & 0xFF, d >> 8])
            if self._noise and self._rng.random() < 0.0005:
                out += bytes([self._rng.randrange(256)])   # simulate a glitch byte
            self._sent += 1
        if out:
            self._push(out)
