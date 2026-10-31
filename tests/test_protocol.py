"""Protocol validation tests.
Shared JSON sensor format check karta hai according to PROTOCOL.md.
"""
import unittest


def validate_sensor_message(payload: dict) -> bool:
    # Source validation: phone, board ya sim hona chahiye
    valid_sources = {"phone", "board", "sim"}
    if payload.get("source") not in valid_sources:
        return False

    # Sensor name non-empty string hona zaroori hai
    sensor = payload.get("sensor")
    if not isinstance(sensor, str) or not sensor.strip():
        return False

    # Values list honi chahiye jisme numbers hon
    values = payload.get("values")
    if not isinstance(values, list) or len(values) == 0:
        return False
    if not all(isinstance(v, (int, float)) for v in values):
        return False

    # Timestamp non-negative number hona chahiye
    time_val = payload.get("time")
    if not isinstance(time_val, (int, float)) or time_val < 0:
        return False

    return True


class TestSensorProtocol(unittest.TestCase):
    def test_valid_phone_accel_payload(self):
        # Normal phone accelerometer data verify karo
        msg = {
            "source": "phone",
            "sensor": "accel",
            "values": [0.12, -9.81, 0.05],
            "time": 1730373000,
        }
        self.assertTrue(validate_sensor_message(msg))

    def test_invalid_source_rejected(self):
        # Invalid source detect hona chahiye
        msg = {
            "source": "unknown_device",
            "sensor": "accel",
            "values": [1.0, 2.0, 3.0],
            "time": 1730373000,
        }
        self.assertFalse(validate_sensor_message(msg))

    def test_invalid_values_rejected(self):
        # String value in values array reject honi chahiye
        msg = {
            "source": "sim",
            "sensor": "accel",
            "values": ["invalid", 2.0],
            "time": 1730373000,
        }
        self.assertFalse(validate_sensor_message(msg))


if __name__ == "__main__":
    unittest.main()

