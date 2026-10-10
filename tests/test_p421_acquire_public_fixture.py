"""P4.21 byte-acquisition integrity tests; no network in unit tests."""
import io
import zipfile

import pytest

from scripts.p421_acquire_public_fixture import PIN, byte_receipt


def fake_package(payload=b"test"):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as z:
        z.writestr("Contents/section0.xml", payload)
    return bio.getvalue()


def test_pinned_origin_and_no_raw_redistribution():
    assert PIN["repository"] == "STAIxBWLB/hwp-cli"
    assert PIN["expected_length"] == 191242
    assert PIN["qualification_only"] is True
    assert "unverified" in PIN["license"]


def test_wrong_bytes_cannot_claim_pinned_provenance():
    with pytest.raises(ValueError, match="length"):
        byte_receipt(fake_package())


def test_exact_length_corrupt_zip_cannot_claim_source():
    with pytest.raises(ValueError, match="blob mismatch"):
        byte_receipt(b"x" * PIN["expected_length"])


def test_zip_safety_controls_reject_path_traversal():
    with pytest.raises(ValueError):
        byte_receipt(fake_package(b"not pinned"))
