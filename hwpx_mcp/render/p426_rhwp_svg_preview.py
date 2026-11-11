"""Optional rhwp SVG page previews; never substitute for Hancom print fidelity.

rhwp CLI: rhwp export-svg <source> -o <dir> --json [--profile screen]
Per upstream CLI docs. Every job runs only against a temporary, owned
HWPX and an empty output directory; source HWPX is not modified.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


class RhwpPreviewUnavailable(RuntimeError):
    pass


def rhwp_capability(executable: str = "rhwp") -> dict:
    found = shutil.which(executable)
    return {
        "engine": "RHWP_SVG_PREVIEW",
        "available": found is not None,
        "binary_detected": found is not None,
        "role": "ALTERNATIVE_PREVIEW_NOT_NATIVE_HANCOM_REFERENCE",
        "supports_page_svg": True,
        "requires_external_rhwp_binary": True,
    }


def render_svg_manifest(
    source: Path,
    output_dir: Path,
    *,
    executable: str = "rhwp",
    timeout_seconds: int = 90,
    profile: str = "screen",
    max_pages: int = 20,
) -> dict:
    if profile not in ("screen", "print", "high-quality", "fast-preview"):
        raise ValueError("RHWP_PROFILE_INVALID")
    if type(timeout_seconds) is not int or not 5 <= timeout_seconds <= 300:
        raise ValueError("RHWP_TIMEOUT_INVALID")
    if type(max_pages) is not int or not 1 <= max_pages <= 100:
        raise ValueError("RHWP_MAX_PAGES_INVALID")
    source = Path(source).resolve(strict=True)
    output_dir = Path(output_dir).resolve(strict=True)
    if source.suffix.lower() != ".hwpx" or not source.is_file():
        raise ValueError("RHWP_INPUT_MUST_BE_HWPX")
    if not output_dir.is_dir() or any(output_dir.iterdir()):
        raise ValueError("RHWP_OUTPUT_DIR_MUST_BE_EMPTY")
    executable_path = shutil.which(executable)
    if not executable_path:
        raise RhwpPreviewUnavailable("RHWP_BINARY_NOT_INSTALLED")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    args = [executable_path, "export-svg", str(source), "-o",
            str(output_dir), "--json", "--profile", profile]
    try:
        proc = subprocess.run(
            args, capture_output=True, timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RhwpPreviewUnavailable("RHWP_RENDER_TIMEOUT") from exc
    if proc.returncode != 0:
        raise RhwpPreviewUnavailable("RHWP_RENDER_FAILED")
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise RuntimeError("RHWP_SOURCE_MUTATED")
    try:
        manifest = json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError("RHWP_INVALID_JSON_MANIFEST") from exc
    if (not isinstance(manifest, dict)
        or manifest.get("format") != "svg"
        or not isinstance(manifest.get("pages"), list)):
        raise RuntimeError("RHWP_MANIFEST_INVALID")
    if len(manifest["pages"]) > max_pages:
        raise ValueError("RHWP_TOO_MANY_PAGES_FOR_PREVIEW")
    pages = []
    for page in manifest["pages"]:
        if not isinstance(page, dict):
            raise RuntimeError("RHWP_PAGE_INVALID")
        path = Path(page.get("path", ""))
        if not path.is_absolute():
            path = output_dir / path
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(output_dir) or resolved.suffix.lower() != ".svg":
            raise RuntimeError("RHWP_UNEXPECTED_SVG_PATH")
        data = resolved.read_bytes()
        if not data or len(data) > 4 * 1024 * 1024:
            raise RuntimeError("RHWP_SVG_BYTES_INVALID")
        if b"<svg" not in data[:1000]:
            raise RuntimeError("RHWP_NOT_AN_SVG")
        pages.append({
            "page": page.get("page"),
            "path": str(resolved),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "overflow_cell_lines": page.get("overflowCellLines"),
        })
    return {
        "engine": "RHWP_SVG_PREVIEW",
        "source_sha256": before,
        "page_count": manifest.get("pageCount"),
        "rendered_count": len(pages),
        "pages": pages,
        "render_authority": "THIRD_PARTY_SVG_NOT_NATIVE_HANCOM",
        "human_visual_review_required": True,
    }
