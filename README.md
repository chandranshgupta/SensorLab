# SensorLab

Real-time sensor data acquisition, simulation, and 3D digital-twin visualization across desktop and mobile devices.

## Status

**Prototype / In Development**: Environment initialized with project preset standard, shared JSON protocol specification, and preflight health checks. Physical board setup proven in Arduino App Lab.

## Prerequisites

- **Python 3.10+** (tested on Python 3.12)
- **Node.js 20+** (v24 tested, required for Electron / Three.js client)
- **Git for Windows** (for pre-commit hooks and preset scripts)
- **Arduino App Lab** (for connecting physical Arduino UNO Q board)

## Quick Start

### 1. Preflight Diagnostics

Check environment readiness and create required data directories:

```bash
python preflight.py --dirs "logs data" --env-example .env.example
```

Or using the launcher on Windows:

```cmd
run.bat diagnose
```

### 2. Run Tests

Run the unit test suite verifying protocol message validation:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Or via launcher:

```cmd
run.bat test
```

### 3. Start the Launcher

Open the interactive self-healing control panel:

```cmd
run.bat
```

## Architecture & Protocol

SensorLab connects real and simulated sensors over a unified JSON protocol over Wi-Fi/WebSockets:
- See `PROTOCOL.md` for the payload specification (`{ source, sensor, values, time }`).
- See `PLAN_DETAILED.md` for detailed roadmap and implementation milestones.
- See `FLOW.md` for telemetry flow and execution paths.

## Licence

Proprietary. All rights reserved. Not open source.

