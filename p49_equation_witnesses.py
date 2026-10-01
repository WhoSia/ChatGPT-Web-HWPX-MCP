from __future__ import annotations

import hashlib
import json
from typing import Any

PHASE = "P4.9"
SCHEMA = "chatgpt-web-hwpx-mcp/p49/equation-alignment-witness/v1"

_CARGO = "x=1 # xxxxxxxxx=22222"

_VARIANTS = {
    "lpile": {
        "eqedit_script": f"LPILE {{{_CARGO}}}",
        "expected_alignment": "LEFT",
        "authority": "HANCOM_NATIVE_PRIMITIVE_WITNESS",
    },
    "pile": {
        "eqedit_script": f"PILE {{{_CARGO}}}",
        "expected_alignment": "CENTER",
        "authority": "HANCOM_NATIVE_PRIMITIVE_WITNESS",
    },
    "rpile": {
        "eqedit_script": f"RPILE {{{_CARGO}}}",
        "expected_alignment": "RIGHT",
        "authority": "HANCOM_NATIVE_PRIMITIVE_WITNESS",
    },
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def alignment_witness_contract() -> dict:
    variants = []
    for variant_id, raw in _VARIANTS.items():
        row = {
            "variant_id": variant_id,
            "cargo": _CARGO,
            **raw,
        }
        row["script_sha256"] = hashlib.sha256(row["eqedit_script"].encode("utf-8")).hexdigest()
        variants.append(row)

    result = {
        "phase": PHASE,
        "schema": SCHEMA,
        "witness_kind": "SAME_CARGO_ALIGNMENT_TRIAD",
        "variants": variants,
        "required_visual_order": ["LEFT", "CENTER", "RIGHT"],
        "adjudication_rule": (
            "PROMOTE_ONLY_IF_THE_SAME_CARGO_VISIBLY_OCCUPIES_DISTINCT_LEFT_CENTER_RIGHT_AXES_"
            "WITHOUT_CLIPPING_OR_CORRUPTION"
        ),
        "p47_frontier_unchanged": True,
        "authority": "P4.9_DISCRIMINATING_WITNESS_DOES_NOT_REWRITE_P4.7_RECEIPTS",
    }
    result["witness_sha256"] = _sha(result)
    return result


def adjudicate_alignment_witness(receipt: dict | None) -> dict:
    contract = alignment_witness_contract()
    if not receipt:
        return {
            "phase": PHASE,
            "status": "WORLD_CONTACT_PENDING",
            "eligible": [],
            "held": ["lpile", "pile"],
            "authority": "NO_NATIVE_VISUAL_RECEIPT_NO_PROMOTION",
        }
    if not isinstance(receipt, dict):
        raise ValueError("receipt must be an object")

    rows = receipt.get("variants")
    if not isinstance(rows, list):
        raise ValueError("receipt.variants must be a list")

    by_id = {str(row.get("variant_id")): row for row in rows if isinstance(row, dict)}
    eligible, held, decisions = [], [], []
    for spec in contract["variants"]:
        variant_id = spec["variant_id"]
        row = by_id.get(variant_id)
        if row is None:
            held.append(variant_id)
            decisions.append({"variant_id": variant_id, "decision": "HOLD_MISSING_NATIVE_EVIDENCE"})
            continue

        hashes_ok = all(
            len(str(row.get(key) or "").lower()) == 64
            for key in ("source_hwpx_sha256", "pdf_sha256")
        )
        expected = spec["expected_alignment"]
        observed = str(row.get("observed_alignment") or "").upper()
        human = str(row.get("human_visual_status") or "").upper()
        good = (
            bool(row.get("export_succeeded"))
            and bool(row.get("no_clipping_or_corruption"))
            and hashes_ok
            and observed == expected
            and human in {"PASS", "PASS_WITH_RESIDUALS"}
        )
        if good:
            eligible.append(variant_id)
            decisions.append({
                "variant_id": variant_id,
                "decision": "PROMOTION_ELIGIBLE",
                "expected_alignment": expected,
                "observed_alignment": observed,
            })
        else:
            held.append(variant_id)
            decisions.append({
                "variant_id": variant_id,
                "decision": "HOLD_EVIDENCE_INCOMPLETE_OR_NEGATIVE",
                "expected_alignment": expected,
                "observed_alignment": observed or "PENDING",
                "human_visual_status": human or "PENDING",
            })

    return {
        "phase": PHASE,
        "status": "ADJUDICATED",
        "eligible": eligible,
        "held": held,
        "decisions": decisions,
        "p47_frontier_unchanged": True,
        "authority": "P4.9_NATIVE_VISUAL_ALIGNMENT_WITNESS_ONLY",
        "adjudication_sha256": _sha(decisions),
    }
