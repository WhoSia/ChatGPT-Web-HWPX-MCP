import unittest

from hwpx_mcp.operations.durable_health import probe_durable_stores


class _Connection:
    def __init__(self, row=(1,)):
        self.row = row
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query):
        self.queries.append(query)
        return self

    def fetchone(self):
        return self.row


class _Store:
    def __init__(self, database_url):
        self.database_url = database_url


class DurableHealthProbeTests(unittest.TestCase):
    def test_probe_deduplicates_shared_database_and_uses_select_one(self):
        calls = []
        connections = []

        def connect(url, *, connect_timeout):
            calls.append((url, connect_timeout))
            conn = _Connection()
            connections.append(conn)
            return conn

        stores = {
            "oauth": _Store("postgres://shared"),
            "documents": _Store("postgres://shared"),
            "evidence": _Store("postgres://shared"),
        }
        result = probe_durable_stores(stores, connect=connect)

        self.assertEqual(result, {name: True for name in stores})
        self.assertEqual(calls, [("postgres://shared", 3)])
        self.assertEqual(connections[0].queries, ["SELECT 1"])

    def test_probe_fails_closed_per_database_and_missing_url(self):
        calls = []

        def connect(url, *, connect_timeout):
            calls.append((url, connect_timeout))
            if url == "postgres://broken":
                raise OSError("unavailable")
            return _Connection(row=(0,))

        result = probe_durable_stores(
            {"broken": _Store("postgres://broken"), "empty": _Store("")},
            connect=connect,
        )

        self.assertEqual(result, {"broken": False, "empty": False})
        self.assertEqual(calls, [("postgres://broken", 3)])

    def test_probe_accepts_dict_row_for_a_distinct_database(self):
        result = probe_durable_stores(
            {"evidence": _Store("postgres://evidence")},
            connect=lambda _url, **_kwargs: _Connection(row={"?column?": 1}),
        )

        self.assertEqual(result, {"evidence": True})


if __name__ == "__main__":
    unittest.main()
