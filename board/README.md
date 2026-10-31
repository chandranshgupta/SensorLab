# SensorLab Board Module

Arduino UNO Q / Arduino App Lab bridge and LED matrix driver for SensorLab.

## Structure

- **`app.yaml`**: App Lab application declaration.
- **`python/main.py`**: Python application running on the Qualcomm Linux MPU. Connects to the laptop's SensorLab Telemetry Hub over Wi-Fi / WebSocket, transmits board sensor telemetry (`temp`), and reflects active sensor intensity onto the 8x13 LED matrix.
- **`sketch/sketch.ino`**: Arduino STM32 MCU sketch that controls the physical LED matrix via `Arduino_RouterBridge` and `Arduino_LED_Matrix`.

## Deployment to Arduino UNO Q

1. Connect the Arduino UNO Q board to your laptop via USB-C.
2. Open **Arduino App Lab**.
3. Open or import this `board` folder as a project in App Lab.
4. Verify Wi-Fi network: ensure your board, laptop, and phone are connected to the same local Wi-Fi or phone hotspot.
5. In `board/python/main.py`, the default hub address is `127.0.0.1` for local tether or set `HUB_HOST` in `.env` to your laptop's Wi-Fi IP (e.g. `10.250.16.210`).
6. Click **Run** in App Lab.
   - The matrix will initialize with the **Good** face (smile).
   - Once telemetry flows, the matrix reflects incoming sensor values dynamically.

## Offline / Desktop Testing

You can test the board Python logic directly on your laptop without the physical board:

```bash
python -m unittest tests/test_board.py
```
