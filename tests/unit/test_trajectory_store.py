# 10Hz Dead Reckoning Backend Engine - SIH 2026
import os
import time
import unittest

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

from moto import mock_aws

from lambdas.common import trajectory_store
from lambdas.common.dynamo import _resource
from tests.unit.dynamo_fixtures import create_device_telemetry_table


def _point(device_id: str, seq: int, timestamp: float, **overrides):
    point = {
        "device_id": device_id,
        "seq": seq,
        "timestamp": timestamp,
        "x": float(seq), "y": float(seq) * 2, "z": 0.0,
        "vx": 1.0, "vy": 0.0, "vz": 0.0,
        "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
        "movement_state": "MOVING",
        "step_count": seq,
        "is_backlog": False,
        "is_verified": True,
        "covariance": [[0.1 if i == j else 0.0 for j in range(9)] for i in range(9)],
    }
    point.update(overrides)
    return point


class TestTrajectoryStore(unittest.TestCase):
    def setUp(self):
        self.mock = mock_aws()
        self.mock.start()
        _resource.cache_clear()
        self.table = create_device_telemetry_table()

    def tearDown(self):
        self.mock.stop()
        _resource.cache_clear()

    def test_get_last_known_position_none_when_no_history(self):
        self.assertIsNone(trajectory_store.get_last_known_position("device_1", table=self.table))

    def test_save_and_get_last_known_position(self):
        base_ts = time.time()
        trajectory_store.save_trajectory_point(_point("device_1", 1, base_ts), table=self.table)
        trajectory_store.save_trajectory_point(_point("device_1", 2, base_ts + 0.1), table=self.table)

        latest = trajectory_store.get_last_known_position("device_1", table=self.table)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["seq_num"], 2)
        self.assertEqual(latest["x"], 2.0)
        self.assertEqual(latest["covariance"][0][0], 0.1)

    def test_get_trajectory_history_orders_oldest_first_and_respects_limit(self):
        base_ts = time.time()
        for i in range(5):
            trajectory_store.save_trajectory_point(_point("device_1", i, base_ts + i * 0.1), table=self.table)

        history = trajectory_store.get_trajectory_history("device_1", limit=3, table=self.table)
        self.assertEqual(len(history), 3)
        self.assertEqual([p["seq_num"] for p in history], [0, 1, 2])

    def test_save_trajectory_batch(self):
        base_ts = time.time()
        points = [_point("device_2", i, base_ts + i * 0.1, is_backlog=True) for i in range(30)]

        count = trajectory_store.save_trajectory_batch(points, table=self.table)
        self.assertEqual(count, 30)

        history = trajectory_store.get_trajectory_history("device_2", limit=100, table=self.table)
        self.assertEqual(len(history), 30)
        self.assertTrue(all(p["is_backlog"] for p in history))

    def test_save_trajectory_batch_empty_list_is_noop(self):
        self.assertEqual(trajectory_store.save_trajectory_batch([], table=self.table), 0)

    def test_devices_are_isolated_by_partition_key(self):
        base_ts = time.time()
        trajectory_store.save_trajectory_point(_point("device_a", 1, base_ts), table=self.table)
        trajectory_store.save_trajectory_point(_point("device_b", 1, base_ts), table=self.table)

        history_a = trajectory_store.get_trajectory_history("device_a", table=self.table)
        history_b = trajectory_store.get_trajectory_history("device_b", table=self.table)
        self.assertEqual(len(history_a), 1)
        self.assertEqual(len(history_b), 1)
        self.assertEqual(history_a[0]["device_id"], "device_a")
        self.assertEqual(history_b[0]["device_id"], "device_b")


if __name__ == "__main__":
    unittest.main()
