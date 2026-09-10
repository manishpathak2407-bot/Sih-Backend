# 10Hz Dead Reckoning Backend Engine - SIH 2026
import os
import unittest

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

from moto import mock_aws

from lambdas.common import connections_store
from lambdas.common.dynamo import _resource
from tests.unit.dynamo_fixtures import create_connections_table


class TestConnectionsStore(unittest.TestCase):
    def setUp(self):
        self.mock = mock_aws()
        self.mock.start()
        _resource.cache_clear()
        self.table = create_connections_table()

    def tearDown(self):
        self.mock.stop()
        _resource.cache_clear()

    def test_register_then_lookup_both_directions(self):
        connections_store.register_connection("conn-abc", "device_1", table=self.table)

        self.assertEqual(
            connections_store.get_device_for_connection("conn-abc", table=self.table), "device_1"
        )
        self.assertEqual(
            connections_store.get_connection_for_device("device_1", table=self.table), "conn-abc"
        )

    def test_unknown_connection_and_device_return_none(self):
        self.assertIsNone(connections_store.get_device_for_connection("no-such-conn", table=self.table))
        self.assertIsNone(connections_store.get_connection_for_device("no-such-device", table=self.table))

    def test_unregister_removes_connection(self):
        connections_store.register_connection("conn-abc", "device_1", table=self.table)
        connections_store.unregister_connection("conn-abc", table=self.table)

        self.assertIsNone(connections_store.get_device_for_connection("conn-abc", table=self.table))
        self.assertIsNone(connections_store.get_connection_for_device("device_1", table=self.table))

    def test_reconnect_overwrites_previous_connection_for_device(self):
        # Mirrors today's behavior where a reconnect just overwrites
        # active_connections[device_id] with the new WebSocket object — the
        # old connectionId is left dangling until its own $disconnect fires
        # (or never, if the old socket died silently), so lookups by device_id
        # should reflect only the newest registered connection.
        connections_store.register_connection("conn-old", "device_1", table=self.table, connected_at=100.0)
        connections_store.register_connection("conn-new", "device_1", table=self.table, connected_at=200.0)

        self.assertEqual(
            connections_store.get_connection_for_device("device_1", table=self.table), "conn-new"
        )


if __name__ == "__main__":
    unittest.main()
