"""SensorLab Arduino UNO Q Bridge & Matrix Driver.
Runs on Qualcomm Linux MPU in Arduino App Lab.
Receives telemetry from laptop hub over WebSocket, updates 8x13 LED matrix,
aur board sensor data laptop hub ko transmit karta hai.
"""

from __future__ import annotations

import base64
import json
import math
import os
import socket
import sys
import threading
import time
from pathlib import Path

# Hardware imports check: App Lab environment mein arduino.app_utils available hota hai
try:
    from arduino.app_utils import App, Bridge, Frame
    import numpy as np
    ON_BOARD = True
except ImportError:
    ON_BOARD = False
    print("[Board] arduino.app_utils nahi mila - offline simulation mode active.")


# 8x13 LED Matrix ke predefined faces (Brightness levels: 0 se 7)
# C0.1 Requirement: Restore the matrix line back to 'good' (happy smile)
FACE_GOOD = [
    [0, 0, 7, 7, 0, 0, 0, 0, 0, 7, 7, 0, 0],
    [0, 0, 7, 7, 0, 0, 0, 0, 0, 7, 7, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 7, 0, 0, 0, 0, 0, 0],
    [7, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7],
    [0, 7, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 0],
    [0, 0, 7, 7, 7, 7, 7, 7, 7, 7, 7, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
]

# Connecting face (dots animation)
FACE_WAIT = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 3, 3, 0, 0, 7, 0, 0, 3, 3, 0, 0],
    [0, 0, 3, 3, 0, 0, 7, 0, 0, 3, 3, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
]


def draw_matrix_frame(grid_2d: list[list[int]]) -> None:
    """LED matrix frame draw karta hai STM32 Bridge call ke zariye."""
    if ON_BOARD:
        frame_arr = np.array(grid_2d, dtype=np.uint8)
        frame_obj = Frame(frame_arr)
        Bridge.call("draw", frame_obj.to_board_bytes())
    else:
        # Offline testing: console pe ASCII representation
        print("[Matrix Display]")
        for row in grid_2d:
            print("".join(" #" if val > 0 else " ." for val in row))


def make_level_bar_frame(level: float) -> list[list[int]]:
    """Sensor value ke hisaab se vertical level bars generate karta hai."""
    # level 0.0 se 1.0 ke beech normalize karo
    norm = max(0.0, min(1.0, level))
    filled_cols = int(norm * 13)
    grid = [[0 for _ in range(13)] for _ in range(8)]
    for r in range(8):
        for c in range(filled_cols):
            grid[r][c] = 5
    return grid


class BoardHubClient:
    """Standard library WebSocket client board side ke liye."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.connected = False

    def connect(self) -> bool:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(3.0)
        try:
            self.sock.connect((self.host, self.port))
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            req = (
                f"GET / HTTP/1.1\r\n"
                f"Host: {self.host}:{self.port}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n\r\n"
            )
            self.sock.sendall(req.encode("ascii"))
            resp = self.sock.recv(1024).decode("utf-8", errors="ignore")
            if "101 Switching Protocols" in resp:
                self.connected = True
                print(f"[Board] Connected to laptop hub at {self.host}:{self.port}")
                return True
        except Exception as err:
            print(f"[Board] Hub connect error: {err}")
        self.connected = False
        return False

    def send_telemetry(self, sensor: str, values: list[float]) -> None:
        """PROTOCOL.md compliant sensor frame laptop hub ko bhejta hai."""
        if not self.connected or not self.sock:
            return

        payload = {
            "source": "board",
            "sensor": sensor,
            "values": values,
            "time": math.floor(time.time()),
        }
        body = json.dumps(payload).encode("utf-8")
        mask = os.urandom(4)
        masked = bytearray(len(body))
        for i in range(len(body)):
            masked[i] = body[i] ^ mask[i % 4]

        header = bytearray([0x81, 0x80 | len(body)])
        frame = header + mask + masked
        try:
            self.sock.sendall(frame)
        except OSError:
            self.connected = False

    def read_message(self) -> dict | None:
        """Incoming telemetry message read karta hai."""
        if not self.connected or not self.sock:
            return None
        try:
            data = self.sock.recv(1024)
            if not data or len(data) < 2:
                return None
            # Text frame payload extract karo
            payload_len = data[1] & 0x7F
            offset = 2
            if payload_len == 126:
                payload_len = int.from_bytes(data[2:4], "big")
                offset = 4
            elif payload_len == 127:
                payload_len = int.from_bytes(data[2:10], "big")
                offset = 10

            text = data[offset : offset + payload_len].decode("utf-8", errors="ignore")
            return json.loads(text)
        except Exception:
            return None

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError as err:
                print(f"[Board] Socket close notice: {err}", file=sys.stderr)
            self.connected = False


def main():
    hub_ip = os.environ.get("HUB_HOST", "127.0.0.1")
    hub_port = int(os.environ.get("PORT", "8080"))

    # Initial state: C0.1 face restore
    print("[Board] Setting LED Matrix to initial 'good' face...")
    draw_matrix_frame(FACE_GOOD)

    client = BoardHubClient(hub_ip, hub_port)

    # Reconnection loop
    print(f"[Board] Connecting to SensorLab Hub at {hub_ip}:{hub_port}...")
    if not client.connect():
        print("[Board] Could not connect to hub. Retrying in background...")
        draw_matrix_frame(FACE_WAIT)

    # Telemetry sender & listener loop
    t = 0.0
    try:
        while True:
            if not client.connected:
                time.sleep(2.0)
                if client.connect():
                    draw_matrix_frame(FACE_GOOD)
                continue

            # Task C1.3: Board sends its simulated temperature / air quality telemetry
            # Waveform for board internal temperature
            temp_c = round(24.5 + 2.0 * math.sin(t * 0.1), 1)
            client.send_telemetry("temp", [temp_c])

            # Laptop hub se incoming messages check karo
            msg = client.read_message()
            if msg and msg.get("type") == "telemetry":
                tdata = msg.get("data", {})
                sensor = tdata.get("sensor")
                values = tdata.get("values", [])

                # C4.2 Sensor usage: incoming sensor values matrix face pe reflect karo
                if sensor == "accel" and len(values) >= 3:
                    # Accelerometer magnitude calculate karo
                    mag = math.sqrt(values[0] ** 2 + values[1] ** 2 + values[2] ** 2)
                    normalized_accel = min(1.0, abs(mag - 9.81) / 5.0)
                    draw_matrix_frame(make_level_bar_frame(normalized_accel))

            t += 1.0
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[Board] Exiting...")
    finally:
        client.close()

    if ON_BOARD:
        App.run()


if __name__ == "__main__":
    main()
