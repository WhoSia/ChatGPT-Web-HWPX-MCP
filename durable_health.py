"""Fast, bounded readiness probes for durable stores."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import psycopg


def probe_durable_stores(
    stores: Mapping[str, Any],
    *,
    connect: Callable[..., Any] = psycopg.connect,
    connect_timeout: int = 3,
) -> dict[str, bool]:
    """Probe each distinct configured database once, without aggregate scans."""
    by_url: dict[str, bool] = {}
    results: dict[str, bool] = {}
    for name, store in stores.items():
        url = str(getattr(store, "database_url", "") or "").strip()
        if not url:
            results[name] = False
            continue
        if url not in by_url:
            try:
                with connect(url, connect_timeout=connect_timeout) as conn:
                    row = conn.execute("SELECT 1").fetchone()
                value = next(iter(row.values())) if isinstance(row, Mapping) else row[0] if row else None
                by_url[url] = value == 1
            except Exception:
                by_url[url] = False
        results[name] = by_url[url]
    return results
