"""SensorLab Software Simulator (Stdlib only, zero-download).
Synthetic sensor telemetry generator jo PROTOCOL.md ke format mein data emit karta hai.
Drone 'rise and fall' aur tilt simulation pattern stream karta hai.
"""

from __future__ import annotations

import base64
import json
import math
import os
import socket
import sys
import time
from pathlib import Path

# Trace kit import karo (prime directive P9 ke mutabiq)
try:
    from simulator.trace_kit import new_trace, touch, traced
except ImportError:
    def traced(fn): return fn
    def touch(*args): pass
    class DummyTrace:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def new_trace(name): return DummyTrace()


class RawWebSocketClient:
    """Zero-dependency standard library RFC 6455 WebSocket client."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None

    def connect(self, timeout: float = 3.0) -> bool:
        # TCP connection establish karo
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        try:
            self.sock.connect((self.host, self.port))
        except Exception as conn_err:
            print(f"[Simulator] Connection fail hui: {conn_err}")
            return False

        # Sec-WebSocket-Key generate karo
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake_req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(handshake_req.encode("ascii"))

        # Handshake response read karo
        resp = self.sock.recv(1024).decode("utf-8", errors="ignore")
        if "101 Switching Protocols" not in resp:
            print(f"[Simulator] Handshake fail: {resp[:100]}")
            return False

        print(f"[Simulator] WebSocket connected to {self.host}:{self.port}")
        return True

    def send_json(self, payload: dict) -> None:
        # JSON payload encode karo
        body = json.dumps(payload).encode("utf-8")
        length = len(body)

        # RFC 6455 client mask zaroori hota hai
        mask = os.urandom(4)
        masked_body = bytearray(length)
        for i in range(length):
            masked_body[i] = body[i] ^ mask[i % 4]

        # Text frame opcode 0x81 (FIN=1, Opcode=1)
        header = bytearray([0x81])
        if length <= 125:
            header.append(0x80 | length)  # Mask bit set karo (0x80)
        elif length <= 65535:
            header.append(0x80 | 126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))

        frame = header + mask + masked_body
        if self.sock:
            self.sock.sendall(frame)

    def close(self) -> None:
        if self.sock:
            try:
                # Close frame 0x88 bhejte hain
                self.sock.sendall(b"\x88\x80\x00\x00\x00\x00")
                self.sock.close()
            except OSError as close_err:
                # Socket already closed ya reset hone par error surface karo
                print(f"[Simulator] Socket close note: {close_err}", file=sys.stderr)


@traced
def generate_drone_frame(t: float) -> tuple[dict, dict]:
    """Drone flight telemetry generate karta hai:
    - Pitch / Roll / Yaw orientation angles (degrees)
    - X / Y / Z Accelerometer readings (m/s^2)
    """
    touch("computation", "drone_physics", "compute")

    # Waveform equations: drone take-off, hover aur gentle bank
    pitch = 12.0 * math.sin(t * 1.2)                  # Pitch tilt in degrees
    roll = 8.0 * math.cos(t * 1.5)                    # Roll bank in degrees
    yaw = (t * 15.0) % 360.0                          # Continuous heading rotation

    # Altitude oscillation (rise and fall)
    az = 9.81 + 1.8 * math.sin(t * 0.8)               # Vertical acceleration
    ax = 1.2 * math.sin(t * 1.2)                      # Lateral sway
    ay = 0.9 * math.cos(t * 1.5)                      # Forward sway

    now_sec = math.floor(time.time())

    orientation_msg = {
        "source": "sim",
        "sensor": "orientation",
        "values": [round(yaw, 1), round(pitch, 1), round(roll, 1)],
        "time": now_sec,
    }

    accel_msg = {
        "source": "sim",
        "sensor": "accel",
        "values": [round(ax, 2), round(ay, 2), round(az, 2)],
        "time": now_sec,
    }

    return orientation_msg, accel_msg


def run_simulator(duration_seconds: float = 0.0, rate_hz: float = 20.0) -> None:
    port = int(os.environ.get("PORT", "8080"))
    client = RawWebSocketClient("127.0.0.1", port)

    print(f"[Simulator] Local telemetry hub dhoond rahe hain port {port} pe...")
    connected = False
    for _ in range(5):
        if client.connect():
            connected = True
            break
        time.sleep(1.0)

    if not connected:
        print(f"[Simulator] Server nahi mila port {port} pe. Pehle 'node server/index.js' chalayein.")
        return

    interval = 1.0 / rate_hz
    start_time = time.time()
    t = 0.0
    frames_sent = 0

    print(f"[Simulator] Streaming drone telemetry @ {rate_hz}Hz (Ctrl+C dabayein rokne ke liye)...")
    try:
        with new_trace("simulator: drone_stream"):
            while True:
                orient_frame, accel_frame = generate_drone_frame(t)

                client.send_json(orient_frame)
                client.send_json(accel_frame)
                frames_sent += 2

                if frames_sent % 40 == 0:
                    print(f"  [Sim Stream] Sent {frames_sent} frames | Pitch: {orient_frame['values'][1]}° | Roll: {orient_frame['values'][2]}° | Az: {accel_frame['values'][2]} m/s²")

                t += interval
                time.sleep(interval)

                if duration_seconds > 0 and (time.time() - start_time) >= duration_seconds:
                    print(f"[Simulator] Duration {duration_seconds}s complete.")
                    break
    except KeyboardInterrupt:
        print("\n[Simulator] Streaming stopped by user.")
    finally:
        client.close()


if __name__ == "__main__":
    # Command line argument se optional duration pass kar sakte hain
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    run_simulator(dur)

