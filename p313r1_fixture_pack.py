from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Callable

from lxml import etree
from hwpx import HwpxDocument


PACK_SCHEMA = "chatgpt-web-hwpx-mcp/pre-hancom-pack/p3.13-r1/v1"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _rewrite_member(path: Path, member: str, mutate: Callable[[etree._Element], None]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == member:
                root = etree.fromstring(payload)
                mutate(root)
                payload = etree.tostring(
                    root, encoding="UTF-8", xml_declaration=True, standalone=True
                )
            target.writestr(info, payload)
    tmp.replace(path)


def _first_section(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as archive:
        names = [
            n for n in archive.namelist()
            if n.startswith("Contents/section") and n.endswith(".xml")
        ]
    if not names:
        raise ValueError("HWPX contains no section XML")
    return sorted(names)[0]


def _scale_primary_char_height(path: Path, basis_points: int) -> dict:
    if basis_points <= 10000:
        raise ValueError("positive-control scale must exceed 10000 basis points")
    changed = {}

    def mutate(root):
        for node in root.iter():
            if _local(node.tag) != "charPr":
                continue
            if "height" not in node.attrib:
                continue
            old = int(node.get("height"))
            new = max(old + 1, round(old * basis_points / 10000))
            node.set("height", str(new))
            changed.update({"old_height": old, "new_height": new})
            return
        raise ValueError("generated HWPX has no mutable primary charPr height")

    _rewrite_member(path, "Contents/header.xml", mutate)
    return changed


def _contract_text_frame(path: Path, right_margin_delta: int) -> dict:
    if right_margin_delta <= 0:
        raise ValueError("right_margin_delta must be positive")
    changed = {}
    section = _first_section(path)

    def mutate(root):
        page_pr = None
        for node in root.iter():
            if _local(node.tag) == "pagePr":
                page_pr = node
                break
        if page_pr is None:
            raise ValueError("generated HWPX has no pagePr")
        margin = None
        for node in page_pr.iter():
            if _local(node.tag) in {"margin", "pageMargin"}:
                margin = node
                break
        if margin is None:
            raise ValueError("generated HWPX has no page margin")
        old = int(margin.get("right", "0"))
        new = old + int(right_margin_delta)
        margin.set("right", str(new))
        changed.update({"old_right_margin": old, "new_right_margin": new})

    _rewrite_member(path, section, mutate)
    return changed


def _validate_minimal_hwpx(path: Path) -> dict:
    required = {
        "mimetype",
        "version.xml",
        "META-INF/container.xml",
        "Contents/content.hpf",
        "Contents/header.xml",
        "Contents/section0.xml",
    }
    if not path.is_file():
        raise FileNotFoundError(path)
    with zipfile.ZipFile(path, "r") as archive:
        names = set(archive.namelist())
        missing = sorted(required - names)
        if missing:
            raise ValueError(f"HWPX missing required entries: {missing}")
        if archive.read("mimetype") != b"application/hwp+zip":
            raise ValueError("invalid HWPX mimetype")
        for name in ("version.xml", "META-INF/container.xml", "Contents/content.hpf", "Contents/header.xml", "Contents/section0.xml"):
            etree.fromstring(archive.read(name))
    return {
        "valid": True,
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _make_document(path: Path, text: str, title: str) -> dict:
    document = HwpxDocument.new()
    if title.strip():
        document.add_paragraph(title.strip())
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        document.add_paragraph(paragraph)
    document.save_to_path(str(path))
    return _validate_minimal_hwpx(path)


def _fixture_text() -> str:
    # Long enough to create several soft-wrap opportunities while retaining
    # natural Korean spacing and identical semantics across source/target.
    sentence = (
        "문단의 의미와 문자는 그대로 유지한 채 글꼴 전진폭과 본문 폭의 아주 작은 "
        "차이가 줄바꿈 경계에서만 관측되도록 구성한 렌더링 민감도 기준 문장입니다."
    )
    return " ".join([sentence] * 8)


def select_boundary_candidate(candidates: list[dict]) -> dict:
    """Select the smallest perturbation whose captured line topology diverges."""
    if not candidates:
        raise ValueError("boundary candidate list is empty")
    ordered = sorted(candidates, key=lambda x: float(x["magnitude"]))
    for item in ordered:
        if item.get("line_break_diverged") is True:
            return {
                "selected": item,
                "selection_rule": "SMALLEST_OBSERVED_LINE_BREAK_DIVERGENCE",
                "authority": "HANCOM_OBSERVED_BOUNDARY_SELECTION",
            }
    return {
        "selected": None,
        "selection_rule": "NO_OBSERVED_TRANSITION",
        "authority": "BOUNDARY_SELECTION_HOLD",
    }


def materialize_pre_hancom_pack(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    from capture_runtime import attach_capture_runtime
    attach_capture_runtime(out_dir)

    text = _fixture_text()
    fixture_specs = [
        {
            "fixture_id": "near-wrap-base",
            "role": "baseline",
            "mutation": "none",
        },
        {
            "fixture_id": "near-wrap-plus-advance",
            "role": "positive-control",
            "mutation": "char-height-scale",
            "basis_points": 10200,
        },
        {
            "fixture_id": "near-wrap-minus-frame",
            "role": "positive-control",
            "mutation": "right-margin-contract",
            "right_margin_delta": 567,
        },
    ]

    fixtures = []
    for spec in fixture_specs:
        fixture_dir = out_dir / spec["fixture_id"]
        fixture_dir.mkdir(parents=True, exist_ok=True)
        source = fixture_dir / "source.hwpx"
        target = fixture_dir / "target.hwpx"

        _make_document(source, text, "P3.13-R1 render fixture")
        shutil.copy2(source, target)

        mutation_receipt = {"type": "none"}
        if spec["mutation"] == "char-height-scale":
            mutation_receipt = {
                "type": "char-height-scale",
                **_scale_primary_char_height(target, int(spec["basis_points"])),
            }
        elif spec["mutation"] == "right-margin-contract":
            mutation_receipt = {
                "type": "right-margin-contract",
                **_contract_text_frame(target, int(spec["right_margin_delta"])),
            }

        source_validation = _validate_minimal_hwpx(source)
        target_validation = _validate_minimal_hwpx(target)
        if not source_validation["valid"] or not target_validation["valid"]:
            raise RuntimeError("fixture mutation produced an invalid HWPX package")

        capture_dir = fixture_dir / "capture"
        capture_dir.mkdir(exist_ok=True)
        placeholders = {
            "line-boxes.json": {
                "schema": "chatgpt-web-hwpx-mcp/line-box-capture/p3.13-r1/v1",
                "fixture_id": spec["fixture_id"],
                "status": "HANCOM_CAPTURE_REQUIRED",
                "source": {"pages": []},
                "target": {"pages": []},
            },
            "fonts.json": {
                "schema": "chatgpt-web-hwpx-mcp/font-inventory/p3.13-r1/v1",
                "fixture_id": spec["fixture_id"],
                "status": "WINDOWS_FONT_ENUMERATION_REQUIRED",
                "fonts": [],
            },
            "render-receipt.template.json": {
                "schema": "chatgpt-web-hwpx-mcp/render-receipt/p3.12/v1",
                "fixture_id": spec["fixture_id"],
                "source_sha256": _sha256_file(source),
                "target_sha256": _sha256_file(target),
                "renderer": {
                    "name": "Hancom Hangul",
                    "version": "",
                    "hancom_native": True,
                    "executable_sha256": "",
                    "os": "Windows",
                    "dpi": 144,
                    "pdf_backend": "",
                    "rasterizer": "",
                    "rasterizer_version": "",
                },
                "source_environment": {"fonts": []},
                "target_environment": {"fonts": []},
                "source_capture": {"pages": []},
                "target_capture": {"pages": []},
                "metrics": {},
                "calibration": {},
            },
        }
        for name, value in placeholders.items():
            (capture_dir / name).write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        fixtures.append({
            **spec,
            "source": str(source.relative_to(out_dir)).replace("\\", "/"),
            "target": str(target.relative_to(out_dir)).replace("\\", "/"),
            "source_sha256": _sha256_file(source),
            "target_sha256": _sha256_file(target),
            "mutation_receipt": mutation_receipt,
            "expected_capture_files": [
                f"{spec['fixture_id']}/capture/source-page-000.png",
                f"{spec['fixture_id']}/capture/target-page-000.png",
                f"{spec['fixture_id']}/capture/line-boxes.json",
                f"{spec['fixture_id']}/capture/fonts.json",
                f"{spec['fixture_id']}/capture/render-receipt.json",
            ],
        })

    # Calibration ladders avoid guessing the exact Hancom wrap threshold.
    calibration = {"advance": [], "frame": []}
    ladder_root = out_dir / "calibration"
    ladder_root.mkdir(exist_ok=True)

    base_source = out_dir / "near-wrap-base" / "source.hwpx"
    for basis_points in (10020, 10040, 10060, 10080, 10100, 10120, 10160, 10200):
        candidate_dir = ladder_root / f"advance-{basis_points}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        source = candidate_dir / "source.hwpx"
        target = candidate_dir / "target.hwpx"
        shutil.copy2(base_source, source)
        shutil.copy2(base_source, target)
        mutation = _scale_primary_char_height(target, basis_points)
        calibration["advance"].append({
            "candidate_id": f"advance-{basis_points}",
            "magnitude": basis_points - 10000,
            "source": str(source.relative_to(out_dir)).replace("\\", "/"),
            "target": str(target.relative_to(out_dir)).replace("\\", "/"),
            "source_sha256": _sha256_file(source),
            "target_sha256": _sha256_file(target),
            "mutation_receipt": mutation,
        })

    for delta in (71, 142, 213, 283, 354, 425, 567, 709):
        candidate_dir = ladder_root / f"frame-{delta}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        source = candidate_dir / "source.hwpx"
        target = candidate_dir / "target.hwpx"
        shutil.copy2(base_source, source)
        shutil.copy2(base_source, target)
        mutation = _contract_text_frame(target, delta)
        calibration["frame"].append({
            "candidate_id": f"frame-{delta}",
            "magnitude": delta,
            "source": str(source.relative_to(out_dir)).replace("\\", "/"),
            "target": str(target.relative_to(out_dir)).replace("\\", "/"),
            "source_sha256": _sha256_file(source),
            "target_sha256": _sha256_file(target),
            "mutation_receipt": mutation,
        })

    manifest = {
        "schema": PACK_SCHEMA,
        "fixture_count": len(fixtures),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "fixtures": fixtures,
        "boundary_calibration_ladder": calibration,
        "boundary_selection_rule": "choose the smallest Hancom-observed line-break divergence separately for advance and frame ladders",
        "hancom_step_remaining": True,
        "manual_fixture_authoring_required": False,
        "authority": "CAPTURE_READY_PRE_HANCOM_FIXTURE_PACK",
    }
    manifest_path = out_dir / "capture-ready-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    zip_path = out_dir.parent / f"{out_dir.name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(out_dir.parent))

    return {
        **manifest,
        "manifest": str(manifest_path),
        "pack_zip": str(zip_path),
        "pack_zip_sha256": _sha256_file(zip_path),
    }
