from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from p335_atlas import build_style_atlas
from p335_corpus import _sha
from p335_registry import registry_snapshot

SCHEMA = "chatgpt-web-hwpx-mcp/p3.42/corpus-coverage-ledger/v1"
GENERALIZATION_SCHEMA = "chatgpt-web-hwpx-mcp/p3.42/design-generalization/v1"
PROBE_STATUSES = ("PASS", "FAIL", "WITHHELD", "NOT_APPLICABLE")
PROBE_IDS = (
    "BYTES_ACQUIRED",
    "PACKAGE_VALID",
    "PARSER_READBACK",
    "ROLE_EVIDENCE",
    "REUSE_RIGHTS_EXPLICIT",
    "PDF_CONTROL_BYTES_INSPECTED",
    "STRUCTURAL_STYLE_GENERALIZATION",
    "VISUAL_STYLE_GENERALIZATION",
)


def corpus_evidence_contract() -> dict:
    return {
        "schema": "chatgpt-web-hwpx-mcp/p3.42/corpus-evidence-contract/v1",
        "phase": "P3.42",
        "workflow": [
            "PROBE_SOURCE",
            "ISSUE_EVIDENCE_TYPED_VERDICT",
            "PRESERVE_WITHHELD_AND_NOT_APPLICABLE",
            "BUILD_DENOMINATOR_EXPLICIT_COVERAGE_LEDGER",
            "DERIVE_CROSS_INSTITUTION_DESCRIPTIVE_CANDIDATES",
            "KEEP_NORMATIVE_AUTHORING_AUTHORITY_SEPARATE",
        ],
        "probe_ids": list(PROBE_IDS),
        "statuses": list(PROBE_STATUSES),
        "denominator_policy": (
            "Every registered source remains visible in the source-level denominator. "
            "Exact-byte duplicates retain provenance but receive one statistical vote in "
            "style-generalization support."
        ),
        "authority": "DESCRIPTIVE_CORPUS_EVIDENCE_ONLY",
        "non_claims": [
            "No metadata-only source is treated as parsed HWPX.",
            "No public-download observation implies open reuse rights.",
            "No declared renderer route is treated as native-render evidence.",
            "No frequent style becomes a normative design default automatically.",
            "No withheld or not-applicable case disappears from the denominator.",
        ],
    }


def _verdict(status: str, reason: str, evidence: Mapping[str, Any] | None = None) -> dict:
    if status not in PROBE_STATUSES:
        raise ValueError(f"invalid probe status: {status}")
    return {
        "status": status,
        "reason": reason,
        "evidence": dict(evidence or {}),
    }


def evaluate_source_probes(row: Mapping[str, Any]) -> dict[str, dict]:
    has_bytes = bool(row.get("sha256")) and int(row.get("byte_size") or 0) > 0
    package_status = str(row.get("package_status") or "NOT_ACQUIRED")
    parser_status = str(row.get("parser_status") or "NOT_RUN")
    role_status = str(row.get("role_status") or "NOT_RUN")
    inclusion = str(row.get("inclusion_status") or "EXCLUDED")
    reuse = str(row.get("reuse_status") or "UNKNOWN_REUSE_RIGHTS")
    controls = list(row.get("controls") or [])
    inspected_controls = [
        item
        for item in controls
        if str(item.get("status") or "") == "PDF_BYTES_INSPECTED_RENDER_ROUTE_DECLARED"
    ]

    verdicts: dict[str, dict] = {}
    verdicts["BYTES_ACQUIRED"] = (
        _verdict(
            "PASS",
            "Owned/acquired source bytes are bound to a SHA-256 receipt.",
            {"sha256": row.get("sha256"), "byte_size": int(row.get("byte_size") or 0)},
        )
        if has_bytes
        else _verdict(
            "WITHHELD",
            "Source is metadata-only; no binary hash or parser claim is available.",
        )
    )

    if not has_bytes:
        verdicts["PACKAGE_VALID"] = _verdict(
            "WITHHELD", "Package validity cannot be tested without source bytes."
        )
    elif package_status == "VALID":
        verdicts["PACKAGE_VALID"] = _verdict(
            "PASS", "HWPX package validation passed.", {"package_status": package_status}
        )
    else:
        verdicts["PACKAGE_VALID"] = _verdict(
            "FAIL", "Acquired bytes did not pass the HWPX package gate.", {"package_status": package_status}
        )

    if package_status != "VALID":
        verdicts["PARSER_READBACK"] = _verdict(
            "WITHHELD", "Parser readback requires a valid acquired HWPX package."
        )
    elif parser_status == "PASS":
        verdicts["PARSER_READBACK"] = _verdict(
            "PASS", "Native parser/readback completed.", {"parser_status": parser_status}
        )
    elif parser_status == "FAILED":
        verdicts["PARSER_READBACK"] = _verdict(
            "FAIL", "Native parser/readback failed.", {"parser_status": parser_status}
        )
    else:
        verdicts["PARSER_READBACK"] = _verdict(
            "WITHHELD", "Parser readback was not performed.", {"parser_status": parser_status}
        )

    if parser_status != "PASS":
        verdicts["ROLE_EVIDENCE"] = _verdict(
            "WITHHELD", "Role evidence requires successful parser readback."
        )
    elif role_status == "PASS":
        verdicts["ROLE_EVIDENCE"] = _verdict(
            "PASS", "At least one textual role has evidence-backed style observations."
        )
    elif role_status == "NO_TEXTUAL_ROLES":
        verdicts["ROLE_EVIDENCE"] = _verdict(
            "NOT_APPLICABLE",
            "The document has no textual roles eligible for the current style-role probe.",
        )
    else:
        verdicts["ROLE_EVIDENCE"] = _verdict(
            "FAIL", "Parser passed but role extraction did not establish usable role evidence.",
            {"role_status": role_status},
        )

    if reuse == "EXPLICIT_OPEN_LICENSE":
        verdicts["REUSE_RIGHTS_EXPLICIT"] = _verdict(
            "PASS",
            "A source-bound explicit open-license statement and license URL are present.",
        )
    elif reuse == "RESTRICTED":
        verdicts["REUSE_RIGHTS_EXPLICIT"] = _verdict(
            "FAIL", "Recorded rights are restricted for reuse."
        )
    else:
        verdicts["REUSE_RIGHTS_EXPLICIT"] = _verdict(
            "WITHHELD",
            "Public accessibility is not treated as permission; reuse rights remain unknown.",
        )

    verdicts["PDF_CONTROL_BYTES_INSPECTED"] = (
        _verdict(
            "PASS",
            "At least one source-bound PDF control was inspected as bytes.",
            {"control_count": len(inspected_controls)},
        )
        if inspected_controls
        else _verdict(
            "WITHHELD",
            "No source-bound inspected PDF control is available; declared metadata alone is insufficient.",
            {"declared_control_count": len(controls)},
        )
    )

    structural_ready = (
        inclusion == "INCLUDED"
        and package_status == "VALID"
        and parser_status == "PASS"
        and role_status == "PASS"
    )
    verdicts["STRUCTURAL_STYLE_GENERALIZATION"] = (
        _verdict(
            "PASS",
            "Source contributes native-XML structural style evidence to the included corpus.",
        )
        if structural_ready
        else _verdict(
            "WITHHELD",
            "Source does not satisfy the included+valid+parser+role structural evidence gate.",
            {
                "inclusion_status": inclusion,
                "package_status": package_status,
                "parser_status": parser_status,
                "role_status": role_status,
            },
        )
    )
    verdicts["VISUAL_STYLE_GENERALIZATION"] = (
        _verdict(
            "PASS",
            "Structural style evidence is paired with at least one inspected PDF control.",
        )
        if structural_ready and inspected_controls
        else _verdict(
            "WITHHELD",
            "Visual generalization requires both structural eligibility and inspected PDF-control bytes.",
            {
                "structural_ready": structural_ready,
                "inspected_pdf_controls": len(inspected_controls),
            },
        )
    )
    return verdicts


def _normalize_probe_ids(probe_ids: Iterable[str] | None) -> list[str]:
    if probe_ids is None:
        return list(PROBE_IDS)
    out: list[str] = []
    for item in probe_ids:
        probe = str(item or "").upper()
        if probe not in PROBE_IDS:
            raise ValueError(f"unknown corpus probe: {item}")
        if probe not in out:
            out.append(probe)
    if not out:
        raise ValueError("at least one corpus probe is required")
    return out


def build_corpus_coverage_ledger(
    records: list[dict],
    *,
    probe_ids: Iterable[str] | None = None,
) -> dict:
    snapshot = registry_snapshot(records)
    probes = _normalize_probe_ids(probe_ids)
    source_rows = []
    by_probe: dict[str, Counter] = {probe: Counter() for probe in probes}
    by_institution: dict[str, Counter] = defaultdict(Counter)

    for row in snapshot["records"]:
        all_verdicts = evaluate_source_probes(row)
        selected = {probe: all_verdicts[probe] for probe in probes}
        for probe, verdict in selected.items():
            by_probe[probe][verdict["status"]] += 1
            by_institution[str(row["institution"])][f"{probe}:{verdict['status']}"] += 1
        source_rows.append(
            {
                "source_id": row["source_id"],
                "source_receipt_sha256": row["source_receipt_sha256"],
                "institution": row["institution"],
                "source_family": row["source_family"],
                "sha256": row.get("sha256"),
                "inclusion_status": row["inclusion_status"],
                "verdicts": selected,
            }
        )

    total = len(source_rows)
    probe_summary = []
    for probe in probes:
        counts = {status: int(by_probe[probe][status]) for status in PROBE_STATUSES}
        evaluated = counts["PASS"] + counts["FAIL"]
        probe_summary.append(
            {
                "probe_id": probe,
                "denominator_total_sources": total,
                "counts": counts,
                "evaluated": evaluated,
                "pass_share_total": round(counts["PASS"] / max(1, total), 8),
                "pass_share_evaluated": (
                    round(counts["PASS"] / evaluated, 8) if evaluated else None
                ),
            }
        )

    unique_byte_hashes = {
        str(row["sha256"])
        for row in snapshot["records"]
        if row.get("sha256") and row["inclusion_status"] == "INCLUDED"
    }
    result = {
        "schema": SCHEMA,
        "phase": "P3.42",
        "registry_sha256": snapshot["registry_sha256"],
        "corpus_sha256": snapshot["corpus_sha256"],
        "probe_ids": probes,
        "source_verdicts": source_rows,
        "probe_summary": probe_summary,
        "denominators": {
            "registered_sources": total,
            "included_sources": snapshot["coverage"]["included"],
            "excluded_sources": snapshot["coverage"]["excluded"],
            "unique_included_byte_documents": len(unique_byte_hashes),
            "exact_duplicate_groups": len(snapshot["exact_duplicates"]),
            "metadata_only_sources": sum(not bool(row.get("sha256")) for row in snapshot["records"]),
        },
        "institution_summary": {
            institution: dict(sorted(counts.items()))
            for institution, counts in sorted(by_institution.items())
        },
        "authority": (
            "PROBE_VERDICT_COVERAGE_LEDGER_DESCRIPTIVE_ONLY_NO_UNOBSERVED_PROMOTION"
        ),
    }
    result["ledger_sha256"] = _sha(result)
    return result


def derive_design_generalizations(
    records: list[dict],
    *,
    ledger: Mapping[str, Any] | None = None,
    min_documents: int = 2,
    min_institutions: int = 2,
    min_document_share: float = 0.2,
) -> dict:
    if min_documents < 1 or min_institutions < 1:
        raise ValueError("support thresholds must be positive")
    if not 0 < float(min_document_share) <= 1:
        raise ValueError("min_document_share must be in (0,1]")

    ledger_obj = (
        dict(ledger)
        if ledger is not None
        else build_corpus_coverage_ledger(records)
    )
    if ledger_obj.get("schema") != SCHEMA:
        raise ValueError("coverage ledger schema mismatch")
    expected_registry = registry_snapshot(records)["registry_sha256"]
    if ledger_obj.get("registry_sha256") != expected_registry:
        raise ValueError("STALE_CORPUS_COVERAGE_LEDGER")

    source_probe_index = {
        row["source_id"]: row["verdicts"]
        for row in ledger_obj.get("source_verdicts", [])
    }
    atlas = build_style_atlas(records)
    candidates = []
    for role in atlas.get("roles", []):
        for candidate in role.get("candidates", []):
            source_ids = list(candidate.get("source_ids") or [])
            structural_sources = [
                source_id
                for source_id in source_ids
                if (
                    source_probe_index.get(source_id, {})
                    .get("STRUCTURAL_STYLE_GENERALIZATION", {})
                    .get("status")
                    == "PASS"
                )
            ]
            if len(structural_sources) != len(source_ids):
                continue
            institutions = list(candidate.get("institutions") or [])
            if (
                int(candidate.get("documents") or 0) < int(min_documents)
                or len(institutions) < int(min_institutions)
                or float(candidate.get("document_share") or 0) < float(min_document_share)
            ):
                continue
            visual_sources = [
                source_id
                for source_id in source_ids
                if (
                    source_probe_index.get(source_id, {})
                    .get("VISUAL_STYLE_GENERALIZATION", {})
                    .get("status")
                    == "PASS"
                )
            ]
            candidates.append(
                {
                    "role": role["role"],
                    "candidate_id": candidate["candidate_id"],
                    "preset_sha256": candidate["preset_sha256"],
                    "authoring_preset": candidate["authoring_preset"],
                    "support": {
                        "documents": candidate["documents"],
                        "document_share": candidate["document_share"],
                        "volume_share": candidate["volume_share"],
                        "institution_balanced_share": candidate[
                            "institution_balanced_share"
                        ],
                        "institutions": institutions,
                        "source_ids": source_ids,
                    },
                    "evidence_class": (
                        "STRUCTURAL_PLUS_INSPECTED_PDF_CONTROL"
                        if len(visual_sources) == len(source_ids) and source_ids
                        else "STRUCTURAL_NATIVE_XML_ONLY"
                    ),
                    "visual_support": {
                        "pass_sources": len(visual_sources),
                        "required_sources": len(source_ids),
                        "complete": len(visual_sources) == len(source_ids)
                        and bool(source_ids),
                    },
                    "authority": (
                        "DESCRIPTIVE_CROSS_INSTITUTION_PATTERN_NOT_NORMATIVE_DEFAULT"
                    ),
                }
            )

    candidates.sort(
        key=lambda item: (
            item["role"],
            -int(item["support"]["documents"]),
            item["candidate_id"],
        )
    )
    result = {
        "schema": GENERALIZATION_SCHEMA,
        "phase": "P3.42",
        "source_ledger_sha256": ledger_obj["ledger_sha256"],
        "source_atlas_sha256": atlas["atlas_sha256"],
        "thresholds": {
            "min_documents": int(min_documents),
            "min_institutions": int(min_institutions),
            "min_document_share": float(min_document_share),
        },
        "status": (
            "CANDIDATES"
            if candidates
            else "INSUFFICIENT_CROSS_INSTITUTION_EVIDENCE"
        ),
        "candidates": candidates,
        "selection_policy": (
            "NO_AUTOMATIC_WINNER; downstream authoring requires explicit strategy/template "
            "selection and keeps structural/visual evidence classes distinct."
        ),
        "authority": "EVIDENCE_GROUNDED_DESCRIPTIVE_GENERALIZATION_ONLY",
    }
    result["generalization_sha256"] = _sha(result)
    return result


__all__ = [
    "GENERALIZATION_SCHEMA",
    "PROBE_IDS",
    "PROBE_STATUSES",
    "SCHEMA",
    "build_corpus_coverage_ledger",
    "corpus_evidence_contract",
    "derive_design_generalizations",
    "evaluate_source_probes",
]
