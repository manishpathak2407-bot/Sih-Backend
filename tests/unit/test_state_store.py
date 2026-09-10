# 10Hz Dead Reckoning Backend Engine - SIH 2026
import os
import unittest

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

from moto import mock_aws

from lambdas.common import state_store
from lambdas.common.dynamo import _resource
from tests.unit.dynamo_fixtures import create_device_telemetry_table


class TestStateStore(unittest.TestCase):
    def setUp(self):
        self.mock = mock_aws()
        self.mock.start()
        _resource.cache_clear()
        self.table = create_device_telemetry_table()

    def tearDown(self):
        self.mock.stop()
        _resource.cache_clear()

    def test_get_device_state_returns_none_for_unknown_device(self):
        self.assertIsNone(state_store.get_device_state("brand_new_device", table=self.table))

    def test_put_then_get_round_trips_state_dict(self):
        state = {
            "x": [[1.0], [2.0], [3.0], [0.5], [0.0], [0.0], [0.1], [0.2], [0.3]],
            "P": [[0.1 if i == j else 0.0 for j in range(9)] for i in range(9)],
            "last_timestamp": 1234567890.5,
            "movement_state": "MOVING",
            "step_count": 42,
            "accel_history": [9.81, 9.9, 10.1],
            "last_step_time": 1234567889.0,
        }

        ok = state_store.put_device_state("device_1", state, table=self.table)
        self.assertTrue(ok)

        restored = state_store.get_device_state("device_1", table=self.table)
        self.assertEqual(restored["x"], state["x"])
        self.assertEqual(restored["P"], state["P"])
        self.assertEqual(restored["last_timestamp"], state["last_timestamp"])
        self.assertEqual(restored["movement_state"], "MOVING")
        self.assertEqual(restored["step_count"], 42)
        self.assertEqual(restored["accel_history"], state["accel_history"])
        self.assertEqual(restored["last_step_time"], state["last_step_time"])
        # Internal bookkeeping attributes must not leak into the state dict
        # handed back to IMUKalmanFilter.from_state_dict().
        self.assertNotIn("PK", restored)
        self.assertNotIn("SK", restored)
        self.assertNotIn("updated_at", restored)

    def test_conditional_write_rejects_stale_timestamp(self):
        state_store.put_device_state(
            "device_1", {"x": [[0.0]] * 9, "P": [[0.0] * 9] * 9, "last_timestamp": 100.0,
                         "movement_state": "REST", "step_count": 0, "accel_history": [], "last_step_time": 0.0},
            table=self.table,
        )

        # A write claiming to be newer than the stored last_timestamp (100.0)
        # must succeed...
        accepted = state_store.put_device_state(
            "device_1", {"x": [[1.0]] * 9, "P": [[0.0] * 9] * 9, "last_timestamp": 101.0,
                         "movement_state": "MOVING", "step_count": 1, "accel_history": [], "last_step_time": 0.0},
            table=self.table, require_newer_than=101.0,
        )
        self.assertTrue(accepted)

        # ...but a write racing in with a stale/older timestamp must be
        # rejected, not silently clobber the newer state. This is the guard
        # against the live-path/backlog-consumer race described in
        # AMPLIFY_MIGRATION.md.
        rejected = state_store.put_device_state(
            "device_1", {"x": [[9.0]] * 9, "P": [[0.0] * 9] * 9, "last_timestamp": 50.0,
                         "movement_state": "REST", "step_count": 0, "accel_history": [], "last_step_time": 0.0},
            table=self.table, require_newer_than=50.0,
        )
        self.assertFalse(rejected)

        # State must reflect the accepted write, not the rejected one.
        current = state_store.get_device_state("device_1", table=self.table)
        self.assertEqual(current["movement_state"], "MOVING")
        self.assertEqual(current["step_count"], 1)

    def test_pending_mode_set_and_consume(self):
        state_store.put_device_state(
            "device_1", {"x": [[0.0]] * 9, "P": [[0.0] * 9] * 9, "last_timestamp": 1.0,
                         "movement_state": "REST", "step_count": 0, "accel_history": [], "last_step_time": 0.0},
            table=self.table,
        )

        state_store.set_pending_mode("device_1", "stationary", table=self.table)
        mode = state_store.consume_pending_mode("device_1", table=self.table)
        self.assertEqual(mode, "stationary")

        # Consuming clears it — a second read finds nothing pending.
        self.assertIsNone(state_store.consume_pending_mode("device_1", table=self.table))

    def test_consume_pending_mode_when_none_set(self):
        state_store.put_device_state(
            "device_1", {"x": [[0.0]] * 9, "P": [[0.0] * 9] * 9, "last_timestamp": 1.0,
                         "movement_state": "REST", "step_count": 0, "accel_history": [], "last_step_time": 0.0},
            table=self.table,
        )
        self.assertIsNone(state_store.consume_pending_mode("device_1", table=self.table))


if __name__ == "__main__":
    unittest.main()
