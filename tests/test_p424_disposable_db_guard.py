"""P4.24 test-DB guard: refuse production-looking URLs without connecting."""
from __future__ import annotations

import unittest

from hwpx_mcp.testing.p424_disposable_database import disposable_test_database_url


class DisposablePostgresGuardTests(unittest.TestCase):
    def setUp(self):
        self.valid = "postgresql://tester:dummy@127.0.0.1:5432/p424_disposable_unit_test_only"

    def test_requires_explicit_opt_in(self):
        with self.assertRaisesRegex(PermissionError, "OPT_IN"):
            disposable_test_database_url(environ={"P424_TEST_DATABASE_URL": self.valid})

    def test_accepts_explicit_local_disposable_database(self):
        env = {
            "P424_TEST_DATABASE_DISPOSABLE": "YES",
            "P424_TEST_DATABASE_URL": self.valid,
        }
        self.assertEqual(disposable_test_database_url(environ=env), self.valid)

    def test_refuses_realistic_production_or_default_database_names(self):
        for target in ["hwpx", "postgres", "template1", "p424_disposable", "p424_disposable_x"]:
            uri = f"postgresql://tester:dummy@localhost:5432/{target}"
            with self.subTest(target=target), self.assertRaisesRegex(PermissionError, "NAME"):
                disposable_test_database_url(environ={
                    "P424_TEST_DATABASE_DISPOSABLE": "YES",
                    "P424_TEST_DATABASE_URL": uri,
                })

    def test_rejects_remote_socket_multi_host_and_hostaddr_override(self):
        uris = [
            "postgresql://tester:dummy@prod.internal:5432/p424_disposable_unit_test_only",
            "postgresql://tester:dummy@127.0.0.1,prod.internal/p424_disposable_unit_test_only",
            "dbname=p424_disposable_unit_test_only user=tester",
            self.valid + "?hostaddr=192.0.2.4",
            self.valid + "?options=-csearch_path%3Dpublic",
        ]
        for uri in uris:
            with self.subTest(uri=uri), self.assertRaises(PermissionError):
                disposable_test_database_url(environ={
                    "P424_TEST_DATABASE_DISPOSABLE": "YES",
                    "P424_TEST_DATABASE_URL": uri,
                })

    def test_missing_url_fails_closed(self):
        with self.assertRaises(ValueError):
            disposable_test_database_url(environ={"P424_TEST_DATABASE_DISPOSABLE": "YES"})


if __name__ == "__main__":
    unittest.main()
