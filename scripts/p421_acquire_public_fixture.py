"""P4.21 ephemeral public HWPX byte acquisition for renderer qualification.

This retrieves ONLY a pinned upstream fixture into a temporary directory.
No raw third-party document bytes are committed or redistributed. An issued
receipt proves downloaded bytes, not native rendering or redistribution rights.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

PIN = {
    "source_id": "hwp-cli-v1.3.1-report-tables",
    "repository": "STAIxBWLB/hwp-cli",
    "commit": "6a10cccfb5e7cc9c88f26a3cd363decde00f5b96",
    "path": "fixtures/samples/report-tables.hwpx",
    "git_blob_sha1": "6475b45d72f0c69f895693aafa26c6eb73805dec",
    "expected_length": 191242,
    "license": "MIT OR Apache-2.0 REPOSITORY; fixture-specific rights unverified",
    "qualification_only": True,
}

MAX_BYTES = 4 * 1024 * 1024


def byte_receipt(data: bytes) -> dict:
    if len(data) != PIN["expected_length"]:
        raise ValueError("Pinned HWPX byte length mismatch")
    if len(data) > MAX_BYTES:
        raise ValueError("Fixture exceeds byte budget")
    gitsha = hashlib.sha1(
        b"blob " + str(len(data)).encode() + b"\0" + data
    ).hexdigest()
    if gitsha != PIN["git_blob_sha1"]:
        raise ValueError("Pinned immutable Git blob mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None:
            raise ValueError("Corrupt ZIP member")
        members = archive.namelist()
        if len(members) > 2000:
            raise ValueError("Excessive ZIP members")
        if not any(name.lower().endswith(".xml") for name in members):
            raise ValueError("HWPX lacks XML package content")
        if any(name.startswith("/") or ".." in Path(name).parts for name in members):
            raise ValueError("Unsafe ZIP member name")
        structure = {
            "zip_members": len(members),
            "xml_members": sum(name.endswith(".xml") for name in members),
        }
    return {
        "schema": "chatgpt-web-hwpx-mcp/p421/ephemeral-fixture-receipt/v1",
        "source_id": PIN["source_id"],
        "source_repository": PIN["repository"],
        "pinned_commit": PIN["commit"],
        "git_blob_sha1_verified": gitsha,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "package_checks": structure,
        "purpose": "RIVAL_RENDERER_QUALIFICATION_ONLY",
        "fresh_pilot_enrolled": False,
        "fixture_specific_license_cleared": False,
        "native_hancom_render_observed": False,
        "source_rights": PIN["license"],
        "raw_bytes_committed": False,
        "raw_bytes_redistributed": False,
    }


def fetch_pinned_bytes() -> bytes:
    url = (
        f"https://raw.githubusercontent.com/{PIN['repository']}/"
        f"{PIN['commit']}/{PIN['path']}"
    )
    errors: list[str] = []
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "P421-fixture-provenance/1.0"}
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError("Download over size budget")
                return data
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            errors.append(type(exc).__name__)
            if attempt < 2:
                time.sleep(1 + attempt)
    raise RuntimeError("REMOTE_ACQUISITION_UNAVAILABLE: " + ",".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="p421-private-bytes-"):
        bytes_ = fetch_pinned_bytes()
        receipt = byte_receipt(bytes_)
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        # The temporary bytes are deliberately not published by Actions.


if __name__ == "__main__":
    main()
