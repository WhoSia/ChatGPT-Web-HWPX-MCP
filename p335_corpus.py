from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from p335_paragraph import build_role_aware_style_exemplars


def _stable(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _source_receipt(item: dict, path: Path) -> dict:
    raw = path.read_bytes()
    return {
        "source_id": str(item.get("source_id") or path.name),
        "institution": str(item.get("institution") or "unknown"),
        "document_label": str(item.get("document_label") or path.name),
        "provenance_url": item.get("provenance_url"),
        "public_status": str(item.get("public_status") or "UNSPECIFIED"),
        "license_note": item.get("license_note"),
        "path_name": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _preset_fingerprint(preset: dict) -> str:
    return _sha(preset)[:20]


def build_corpus_style_profile(items: list[dict]) -> dict:
    """Aggregate multiple HWPX exemplars while preserving per-source provenance."""
    if not items:
        raise ValueError("At least one corpus item is required")

    sources = []
    role_rows = []
    institution_counts = Counter()
    institutional_role_counts: dict[str, Counter] = defaultdict(Counter)

    for item in items:
        if not isinstance(item, dict) or not item.get("path"):
            raise ValueError("Each corpus item requires path")
        path = Path(str(item["path"]))
        if not path.exists():
            raise FileNotFoundError(path)

        receipt = _source_receipt(item, path)
        profile = build_role_aware_style_exemplars(path)
        source_row = {**receipt, "role_profile_sha256": profile.get("profile_sha256"), "roles": []}
        institution = receipt["institution"]
        institution_counts[institution] += 1

        for role in profile.get("roles", []):
            preset = role.get("authoring_preset") or {}
            fingerprint = _preset_fingerprint(preset)
            row = {
                "source_id": receipt["source_id"],
                "institution": institution,
                "role": role.get("role"),
                "paragraph_count": int(role.get("paragraph_count") or 0),
                "weighted_characters_or_empty_paragraphs": int(role.get("weighted_characters_or_empty_paragraphs") or 0),
                "preset_fingerprint": fingerprint,
                "authoring_preset": preset,
                "paragraph_profile_sha256": role.get("paragraph_profile_sha256"),
                "native_readback": role.get("native_readback"),
            }
            source_row["roles"].append(row)
            role_rows.append(row)
            institutional_role_counts[institution][str(row["role"])] += 1

        sources.append(source_row)

    role_summary = []
    roles = sorted({str(row["role"]) for row in role_rows})
    for role in roles:
        rows = [row for row in role_rows if str(row["role"]) == role]
        total_weight = sum(row["weighted_characters_or_empty_paragraphs"] for row in rows)
        fingerprints = Counter(row["preset_fingerprint"] for row in rows)
        candidates = []
        for fingerprint, documents in fingerprints.most_common():
            matching = [row for row in rows if row["preset_fingerprint"] == fingerprint]
            weight = sum(row["weighted_characters_or_empty_paragraphs"] for row in matching)
            institutions = sorted({row["institution"] for row in matching})
            candidates.append({
                "preset_fingerprint": fingerprint,
                "documents": documents,
                "document_share": round(documents / max(1, len(rows)), 6),
                "weighted_characters_or_empty_paragraphs": weight,
                "weight_share": round(weight / max(1, total_weight), 6),
                "institutions": institutions,
                "authoring_preset": matching[0]["authoring_preset"],
                "source_ids": [row["source_id"] for row in matching],
            })
        role_summary.append({
            "role": role,
            "documents_with_role": len(rows),
            "total_weight": total_weight,
            "distinct_presets": len(fingerprints),
            "consensus_candidates": candidates[:20],
        })

    institution_summary = []
    for institution in sorted(institution_counts):
        institution_summary.append({
            "institution": institution,
            "documents": institution_counts[institution],
            "role_document_counts": dict(sorted(institutional_role_counts[institution].items())),
        })

    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.35/corpus-style-profile/v1",
        "phase": "P3.35-R3",
        "document_count": len(sources),
        "source_receipts": sources,
        "institution_summary": institution_summary,
        "role_summary": role_summary,
        "selection_policy": {
            "default": "NO_AUTOMATIC_WINNER",
            "guidance": "Expose prevalence, weight, institutions and provenance-preserving candidate presets; never collapse heterogeneous institutions or roles into one global style.",
            "public_corpus_policy": "Prefer public or openly downloadable HWPX sources; record provenance URL, public status and license note; retain source hashes for later audit.",
        },
    }
    result["profile_sha256"] = _sha(result)
    return result


def build_style_library(corpus_profile: dict, *, min_documents: int = 2, min_share: float = 0.25) -> dict:
    """Create a reusable candidate library without inventing normative style authority."""
    entries = []
    for role in corpus_profile.get("role_summary", []):
        for candidate in role.get("consensus_candidates", []):
            if int(candidate.get("documents") or 0) < int(min_documents):
                continue
            if float(candidate.get("document_share") or 0.0) < float(min_share):
                continue
            entries.append({
                "library_id": f"{role['role']}:{candidate['preset_fingerprint']}",
                "role": role["role"],
                "authoring_preset": candidate["authoring_preset"],
                "support": {
                    "documents": candidate["documents"],
                    "document_share": candidate["document_share"],
                    "weight_share": candidate["weight_share"],
                    "institutions": candidate["institutions"],
                    "source_ids": candidate["source_ids"],
                },
                "authority": "EVIDENCE_GUIDED_REUSABLE_CANDIDATE_NOT_NORMATIVE_DEFAULT",
            })
    result = {
        "schema": "chatgpt-web-hwpx-mcp/p3.35/style-library/v1",
        "source_profile_sha256": corpus_profile.get("profile_sha256"),
        "minimum_documents": int(min_documents),
        "minimum_document_share": float(min_share),
        "entries": entries,
    }
    result["library_sha256"] = _sha(result)
    return result
