# SensorLab: Detailed Plan



## The two problems

**Problem 1: Sensor connector and usage.**
Get sensors (phone motion, board readings, later Modulino modules) into the system, read their values, send them, and react to them. A simulator covers the time when no hardware is connected.

**Problem 2: Visualization on laptop and mobile.**
Show the board, its sensors, and the live connections in 3D on both the laptop and the phone. Sensors can be added or removed while the app is running.

---

## Problem 1: Sensor connector and usage

**Solution:** every sensor, real or simulated, sends messages in one shared format over Wi-Fi. The USB-C cable is for setup and power only.

Shared format (defined in C1.1):
`{ "source": "phone|board|sim", "sensor": "accel", "values": [x, y, z], "time": 1234567890 }`

Tasks:

- [x] **C0 Setup (done):** board connected through App Lab, clock fixed, example apps run, matrix control proven, personal copy `My Sensor Test` saved on the board.
- [ ] **C0.1 Restore the matrix line changed in testing back to `good`.**
- [ ] **C0.2 Hotspot test:** board, laptop, and phone on the same phone hotspot.
- [ ] **C1.1 Message format spec (`PROTOCOL.md`).**
  - Acceptance: every module below uses only this format.
- [ ] **C1.2 Board listener:** the board's Python app accepts messages on a port and prints them in App Lab's log.
  - Acceptance: a test message from the laptop shows in App Lab's log.
- [ ] **C1.3 Board sends its own readings** to the laptop app.
  - Acceptance: the laptop app receives board readings.
- [ ] **C2.1 Phone sensor sender:** a web page on the phone reads motion data and sends it in the shared format over WebSocket.
  - Acceptance: tilting the phone changes the values on the laptop.
- [ ] **C2.2 iPhone support:** HTTPS and the motion permission prompt.
- [ ] **C3.1 Laptop receiver:** a WebSocket server in the desktop app receives messages from the board and the phone.
  - Acceptance: a test client sends a message and the app logs it.
- [ ] **C4.1 Simulator:** generates messages in the same format, starting with a "drone rises and falls" preset.
  - Acceptance: the simulator drives a sensor the same way a real one would.
- [ ] **C4.2 Sensor usage:** pick a sensor, see its latest values, and send them to the board's matrix.
  - Acceptance: a chosen sensor changes the matrix face.

---

## Problem 2: Visualization on laptop and mobile

**Solution:** one 3D web page (Three.js, low-poly style) that runs in the laptop app and in the phone's browser. The laptop app serves the page on the local network. The phone opens it by address, so both screens show the same live scene.

Tasks:

- [ ] **V1.1 Desktop shell:** Electron window on Windows that opens the 3D page.
  - Acceptance: starting the app opens the window. Requires Node.js on the laptop.
- [ ] **V1.2 3D scene:** the UNO Q board (low-poly) in the middle, orbit camera, simple lighting.
  - Acceptance: runs smoothly on the laptop.
- [ ] **V2.1 Sensor objects:** each sensor is a 3D object placed in orbit around the board.
- [ ] **V2.2 Add and remove sensors:** buttons add or remove sensors with a short animation.
  - Acceptance: adding and removing works without restarting.
- [ ] **V2.3 Live connection lines:** a line from each sensor to the board, with pulses when data arrives.
- [ ] **V2.4 Sensor panel:** latest values for the selected sensor.
- [ ] **V3.1 Phone view:** the laptop app serves the same page on the local network. The phone opens it using the address shown in the app.
  - Acceptance: the phone shows the same scene, and it updates when the laptop does.
- [ ] **V3.2 Phone layout:** touch controls for rotate and zoom, buttons sized for a thumb.
  - Acceptance: works at phone width with no horizontal scrolling.
- [ ] **V4.1 Packaging:** Windows installer or portable build.
- [ ] **V4.2 Native phone app (later, only if the browser view falls short).**
- [ ] **V5.1 Look:** colors, low-poly board model, sensor icons.

---

## Where we've reached

**Done:**

- Board connected through App Lab, clock fixed, Blink and Blink with UI ran, air quality example runs.
- Personal copy `My Sensor Test` saved on the board.
- A matrix face was changed and confirmed on the board.
- Project folder `F:\Carrer\Projects\SensorLab` created.

**Not done:**

- Everything in both problems above, starting with C0.1 and C0.2.

**Notes:**

- Node.js must be installed on the laptop before V1.1.
- The air quality example uses the `demo` API token. A real token may be needed for steady data.

---

## Approach to make it good

1. **Thin vertical slice first.** Get one sensor from phone to laptop to 3D view before adding anything else. A working small loop beats a large unfinished system.
2. **Message format first.** Everything depends on it, so it's specified and fixed before any module is coded.
3. **Simulator before hardware.** The simulator lets the 3D view and sensor logic be built and tested without waiting on the board or phone.
4. **One test per step.** Each task has an acceptance check you can run yourself. A task isn't done until its check passes.
5. **Visible state.** Every module logs what it receives and sends, so problems show up in App Lab's log or the app's log, not as silence.
6. **Swappable sources.** Real sensors, the simulator, and later AI-generated scenarios all feed the same path, so one can replace another without changing the display.
7. **Small, reversible changes.** Each change is committed on its own, so any step can be undone.
8. **Mobile is a constraint from the start.** The 3D view is designed for phone width and touch from the first version, not added later.
9. **Keep secrets out of the project.** API keys live in the app's settings only, never in code or the repository.
10. **Measure before optimizing.** Check frame rate and message delay on real hardware before tuning anything.

---

## Next step

C0.1 (restore the matrix line) and C0.2 (hotspot test). After those, C1.1 (the message format) starts.
