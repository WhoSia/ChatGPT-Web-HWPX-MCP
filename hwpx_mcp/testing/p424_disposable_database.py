"""Strict opt-in guard for P4.24 destructive integration-test connections.

An arbitrary URL and YES flag are not enough: the test database must have
a clearly disposable name and reside on a local PostgreSQL instance. This
does not make it safe to use a production server over a local tunnel.
The test operator must still provision a separate disposable database.
"""
from __future__ import annotations

import ipaddress
import os

from psycopg.conninfo import conninfo_to_dict


def disposable_test_database_url(*, environ=None) -> str:
    env = os.environ if environ is None else environ
    if env.get("P424_TEST_DATABASE_DISPOSABLE") != "YES":
        raise PermissionError("P424_DISPOSABLE_DB_EXPLICIT_OPT_IN_REQUIRED")
    url = env.get("P424_TEST_DATABASE_URL", "")
    if not url:
        raise ValueError("P424_DISPOSABLE_DB_URL_REQUIRED")
    try:
        parsed = conninfo_to_dict(url)
    except Exception as exc:
        raise ValueError("P424_DISPOSABLE_DB_URL_INVALID") from exc

    database = parsed.get("dbname", "")
    host = parsed.get("host", "")
    hostaddr = parsed.get("hostaddr", "")
    if not database.startswith("p424_disposable_") or len(database) < 24:
        raise PermissionError("P424_DISPOSABLE_DB_NAME_REQUIRED")
    # Reject socket/default host, hostname lookalikes, multi-host failover,
    # service mappings and connection URI query overrides.
    if parsed.get("service") or not host or "," in host:
        raise PermissionError("P424_DISPOSABLE_DB_LOCAL_HOST_REQUIRED")
    if host != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise PermissionError("P424_DISPOSABLE_DB_LOCAL_HOST_REQUIRED")
        except ValueError as exc:
            raise PermissionError("P424_DISPOSABLE_DB_LOCAL_HOST_REQUIRED") from exc
    if hostaddr:
        try:
            if not ipaddress.ip_address(hostaddr).is_loopback:
                raise PermissionError("P424_DISPOSABLE_DB_LOCAL_HOST_REQUIRED")
        except ValueError as exc:
            raise PermissionError("P424_DISPOSABLE_DB_LOCAL_HOST_REQUIRED") from exc
    if parsed.get("options"):
        raise PermissionError("P424_DISPOSABLE_DB_UNEXPECTED_OPTIONS")
    return url
