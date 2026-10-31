# SensorLab Unified Protocol Spec

This document specifies the shared sensor message format used across all SensorLab devices and modules (Arduino UNO Q board, smartphones, laptop WebSocket server, and software simulator).

## Message Format

Every telemetry frame is a UTF-8 JSON object with the following fields:

```json
{
  "source": "phone|board|sim",
  "sensor": "accel|gyro|temp|air_quality",
  "values": [0.0, 0.0, 0.0],
  "time": 1730373000
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `source` | `string` | The originator: `"phone"`, `"board"`, or `"sim"`. |
| `sensor` | `string` | Sensor identifier (e.g. `"accel"`, `"gyro"`, `"temp"`). |
| `values` | `array of numbers` | Numerical measurements (e.g. `[x, y, z]` coordinates or readings). |
| `time` | `integer or float` | Unix timestamp in seconds or milliseconds. |

## Validation Rules

1. `source` must be one of `"phone"`, `"board"`, or `"sim"`.
2. `sensor` must be a non-empty string.
3. `values` must be an array of numeric values (floats or integers).
4. `time` must be a non-negative number.

