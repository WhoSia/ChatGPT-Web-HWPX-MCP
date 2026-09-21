from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from p315_replay_builder import build_version_record
from p316_version_indexed import (
    SCHEMA,
    adjudicate_version_indexed_stability,
    build_structural_oracle,
    compare_structural_oracles,
)


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _fixture_diff(pack: Path, fixture_id: str) -> dict:
    source = build_structural_oracle(pack / fixture_id / "source.hwpx")
    target = build_structural_oracle(pack / fixture_id / "target.hwpx")
    return {
        "fixture_id": fixture_id,
        "source_structural_oracle_sha256": source["structural_oracle_sha256"],
        "target_structural_oracle_sha256": target["structural_oracle_sha256"],
        "diff": compare_structural_oracles(source, target),
    }


def build_structural_consolidation(pack_dir: Path) -> dict:
    pack = Path(pack_dir)
    baseline = _fixture_diff(pack, "near-wrap-base")
    advance = _fixture_diff(pack, "near-wrap-plus-advance")
    frame = _fixture_diff(pack, "near-wrap-minus-frame")

    result = {
        "baseline": baseline,
        "advance": advance,
        "frame": frame,
        "baseline_structurally_identical": baseline["diff"]["structurally_identical"],
        "advance_changed_dimensions": advance["diff"]["changed_dimensions"],
        "frame_changed_dimensions": frame["diff"]["changed_dimensions"],
        "authority": "RENDERER_INDEPENDENT_STRUCTURAL_ORACLE_CONSOLIDATION",
    }
    result["structural_consolidation_sha256"] = _sha(result)
    return result


def build_version_indexed_packet(
    repetition_pairs: list[tuple[Path, Path]],
) -> dict:
    if len(repetition_pairs) < 3:
        raise ValueError("at least three repetition pack/font-custody pairs are required")

    records = [
        build_version_record(Path(pack), Path(font_custody))
        for pack, font_custody in repetition_pairs
    ]
    structural = build_structural_consolidation(Path(repetition_pairs[0][0]))

    packet = {
        "schema": SCHEMA,
        "repetitions": records,
        "structural_oracle": structural,
    }
    packet["packet_sha256"] = _sha(packet)
    packet["adjudication"] = adjudicate_version_indexed_stability(packet)
    return packet
