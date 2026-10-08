"""Read-only public P4.18-P3 host reachability smoke.

Probes an intentionally nonexistent workflow via GET only. Never sends
credentials, stages approvals, or modifies any HWPX document.
"""
from __future__ import annotations

import os
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit

BASE = os.environ.get("P418_PUBLIC_SMOKE_BASE", "https://chatgpt-web-hwpx-mcp-p0.onrender.com").rstrip("/")
if urlsplit(BASE).scheme != "https":
    raise SystemExit("HTTPS public production URL required")


def probe(path: str) -> tuple[int, str, dict]:
    request = urllib.request.Request(BASE + path, headers={
        "User-Agent": "HWPX-P418-ReadOnlyHostSmoke/1.0",
        "Accept": "text/html,application/json",
    }, method="GET")
    try:
        response = urllib.request.urlopen(request, timeout=35, context=ssl.create_default_context())
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(32768).decode("utf-8", "replace")
        return response.status, body, dict(response.headers.items())


health, body, _ = probe("/health")
if health != 200:
    raise SystemExit(f"Health endpoint returned HTTP {health}")
print("Production /health HTTP 200 PASS")

# A valid-shaped but nonexistent workflow must not expose a real document.
status, body, headers = probe("/p418/host/review?workflow_id=read-only-smoke-000000000001")
if status != 200:
    raise SystemExit(f"Human-review GET endpoint unavailable: HTTP {status}")
if "HWPX 변경 내용 확인" not in body or "변경 내용 보기" not in body:
    raise SystemExit("Human-review login form missing")
if "approval_key" in body or "lease_token" in body:
    raise SystemExit("Unexpected internal credential marker on public review page")
normalized_headers = {name.lower(): value for name, value in headers.items()}
if "no-store" not in normalized_headers.get("cache-control", "").lower():
    raise SystemExit("No-store protection absent")
if "frame-ancestors 'none'" not in normalized_headers.get("content-security-policy", ""):
    print("Observed response header names:", sorted(normalized_headers))
    raise SystemExit("Frame protection absent")
print("Public P4.18 independent review GET/caching/CSP PASS")
print("This is READ-ONLY reachability; human approval and native document E2E remain unverified.")
