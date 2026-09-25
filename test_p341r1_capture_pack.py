from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from p341r1_capture_pack import (
    FIXTURES,
    FROZEN_BENCHMARK_COMMIT,
    FROZEN_MATERIALIZATION_METHOD,
    deterministic_zip,
    validate_complete,
    write_json,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_frozen_a3_identity_is_explicit_and_cross_archetype():
    assert FROZEN_BENCHMARK_COMMIT == "7872a8a5cf063c547f65ccd823d1063a51c17ee1"
    assert FROZEN_MATERIALIZATION_METHOD == "REPOSITORY_SEALED_WORKFLOW_ARTIFACT_BYTES_EXACT_SHA256"
    assert len(FROZEN_ARTIFACT_SHARDS) == 4
    assert all(path.startswith("benchmarks/frozen/p341/") for path in FROZEN_ARTIFACT_SHARDS)
    assert [x["archetype"] for x in FIXTURES] == [
        "RESEARCH_BRIEF",
        "INSTITUTIONAL_REPORT",
        "ACADEMIC_REPORT",
    ]
    assert len({x["sha256"] for x in FIXTURES}) == 3
    assert all(len(x["sha256"]) == 64 for x in FIXTURES)
    assert all(len(x["content_sha256"]) == 64 for x in FIXTURES)


def test_complete_validation_requires_native_diagnostic_authority():
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp) / "pack"
        pack.mkdir()
        entries = []
        for index, frozen in enumerate(FIXTURES):
            fixture_dir = pack / "fixtures" / frozen["fixture_id"]
            capture_dir = fixture_dir / "capture"
            capture_dir.mkdir(parents=True)
            payload = f"fixture-{index}".encode()
            input_path = fixture_dir / "input.hwpx"
            input_path.write_bytes(payload)
            actual = _sha(payload)
            entries.append({
                **frozen,
                "path": input_path.relative_to(pack).as_posix(),
                "sha256": actual,
                "size": len(payload),
            })
            write_json(capture_dir / "render-receipt.json", {
                "source_sha256": actual,
                "capture": {"pages": [{"page_index": 0, "raster_sha256": "a" * 64}]},
            })
            write_json(capture_dir / "page-composition-diagnostic.json", {
                "authority": "HANCOM_NATIVE_RENDER_EVIDENCE",
                "world_contact_valid": True,
                "page_count": 1,
                "verdict": "PASS",
                "finding_count": 0,
            })

        write_json(pack / "capture-ready-manifest.json", {
            "schema": "authorbench/p341r1-hancom-capture-pack/v1",
            "fixtures": entries,
        })
        result = validate_complete(pack)
        assert result["complete"] is True
        assert result["authority"] == "NATIVE_HANCOM_A3_PAGE_COMPOSITION_COMPLETE"
        assert len(result["receipts"]) == 3

        first = pack / "fixtures" / entries[0]["fixture_id"] / "capture" / "page-composition-diagnostic.json"
        broken = json.loads(first.read_text(encoding="utf-8"))
        broken["authority"] = "EXTERNAL_RENDER_OBSERVATION"
        write_json(first, broken)
        failed = validate_complete(pack)
        assert failed["complete"] is False
        assert failed["authority"] == "INCOMPLETE_NATIVE_WORLD_CONTACT"


def test_capture_zip_is_deterministic_for_same_pack():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pack = root / "pack"
        pack.mkdir()
        (pack / "a.txt").write_text("alpha", encoding="utf-8")
        (pack / "b.txt").write_text("beta", encoding="utf-8")
        one = root / "one.zip"
        two = root / "two.zip"
        digest_one = deterministic_zip(pack, one)
        digest_two = deterministic_zip(pack, two)
        assert digest_one == digest_two
        assert one.read_bytes() == two.read_bytes()
