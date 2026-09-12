from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from xml.etree import ElementTree

from hwpx import HwpxDocument
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse

PROJECT = "ChatGPT Web HWPX MCP"
VERSION = "0.2.0-p1"

mcp = MCPServer(
    PROJECT,
    instructions=(
        "P1 HWPX materialization service for ChatGPT Web. "
        "Use create_document to create a small HWPX from text, then inspect_document "
        "and export_document for a short-lived download URL. Existing-document ingest "
        "is intentionally not enabled in P1."
    ),
)

OBJECT_DIR = Path(os.environ.get("P1_OBJECT_DIR", "/tmp/chatgpt-web-hwpx-mcp-p1"))
OBJECT_DIR.mkdir(parents=True, exist_ok=True)
ACCESS_TOKEN = os.environ.get("P1_ACCESS_TOKEN", "")
DOWNLOAD_SECRET = os.environ.get("P1_DOWNLOAD_SECRET", "")
DOC_TTL_SECONDS = max(300, min(int(os.environ.get("P1_DOC_TTL_SECONDS", "1800")), 86400))
MAX_TEXT_CHARS = max(1000, min(int(os.environ.get("P1_MAX_TEXT_CHARS", "100000")), 500000))
DOC_ID_RE = re.compile(r"^doc_[A-Za-z0-9_-]{20,64}$")
REQUIRED_HWPX_ENTRIES = {
    "mimetype",
    "version.xml",
    "META-INF/container.xml",
    "Contents/content.hpf",
    "Contents/header.xml",
    "Contents/section0.xml",
}


def _utc_iso(timestamp: float | None = None) -> str:
    if timestamp is None:
        timestamp = time.time()
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _require_access_token(access_token: str) -> None:
    if not ACCESS_TOKEN:
        raise RuntimeError("P1_ACCESS_TOKEN is not configured on the server")
    if not secrets.compare_digest(access_token, ACCESS_TOKEN):
        raise ValueError("Invalid P1 access token")


def _download_secret() -> bytes:
    if not DOWNLOAD_SECRET:
        raise RuntimeError("P1_DOWNLOAD_SECRET is not configured on the server")
    return DOWNLOAD_SECRET.encode("utf-8")


def sanitize_filename(filename: str) -> str:
    name = Path(filename or "document.hwpx").name
    name = re.sub(r"[^0-9A-Za-z._\-가-힣 ]+", "_", name).strip(" .")
    if not name:
        name = "document.hwpx"
    if not name.lower().endswith(".hwpx"):
        name += ".hwpx"
    stem = Path(name).stem[:64] or "document"
    return f"{stem}.hwpx"


def _new_document_id() -> str:
    return "doc_" + secrets.token_urlsafe(18)


def _paths(document_id: str) -> tuple[Path, Path]:
    if not DOC_ID_RE.fullmatch(document_id):
        raise ValueError("Invalid document_id")
    return OBJECT_DIR / f"{document_id}.hwpx", OBJECT_DIR / f"{document_id}.json"


def _write_metadata(document_id: str, metadata: dict) -> None:
    _, metadata_path = _paths(document_id)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_metadata(document_id: str, *, allow_expired: bool = False) -> dict:
    hwpx_path, metadata_path = _paths(document_id)
    if not hwpx_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError("Unknown document_id")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not allow_expired and float(metadata["expires_at_epoch"]) <= time.time():
        _delete_document_files(document_id)
        raise FileNotFoundError("Document expired")
    return metadata


def _delete_document_files(document_id: str) -> bool:
    hwpx_path, metadata_path = _paths(document_id)
    removed = False
    for path in (hwpx_path, metadata_path):
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed


def _cleanup_expired() -> None:
    now = time.time()
    for metadata_path in OBJECT_DIR.glob("doc_*.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if float(metadata.get("expires_at_epoch", 0)) <= now:
                document_id = metadata_path.stem
                if DOC_ID_RE.fullmatch(document_id):
                    _delete_document_files(document_id)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue


def validate_hwpx_package(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if not infos:
            raise ValueError("Empty HWPX package")
        if infos[0].filename != "mimetype":
            raise ValueError("HWPX mimetype must be the first ZIP entry")
        if infos[0].compress_type != zipfile.ZIP_STORED:
            raise ValueError("HWPX mimetype must be stored without compression")

        names = {info.filename for info in infos}
        missing = sorted(REQUIRED_HWPX_ENTRIES - names)
        if missing:
            raise ValueError(f"Missing required HWPX entries: {', '.join(missing)}")

        if archive.read("mimetype") != b"application/hwp+zip":
            raise ValueError("Invalid HWPX mimetype signature")

        for xml_name in (
            "version.xml",
            "META-INF/container.xml",
            "Contents/content.hpf",
            "Contents/header.xml",
            "Contents/section0.xml",
        ):
            payload = archive.read(xml_name)
            if len(payload) > 8_000_000:
                raise ValueError(f"Generated XML entry is unexpectedly large: {xml_name}")
            ElementTree.fromstring(payload)

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "valid": True,
        "sha256": digest,
        "bytes": path.stat().st_size,
        "required_entries": sorted(REQUIRED_HWPX_ENTRIES),
    }


def materialize_hwpx(path: Path, text: str, title: str = "") -> dict:
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"text exceeds P1_MAX_TEXT_CHARS={MAX_TEXT_CHARS}")
    if not text.strip() and not title.strip():
        raise ValueError("Document must contain title or text")

    document = HwpxDocument.new()
    if title.strip():
        document.add_paragraph(title.strip())
    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save_to_path(str(path))
    return validate_hwpx_package(path)


def _public_base_url() -> str:
    explicit = os.environ.get("P1_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if host:
        return f"https://{host}"
    return "http://127.0.0.1:8000"


def _download_signature(document_id: str, expires_at: int) -> str:
    payload = f"{document_id}:{expires_at}".encode("utf-8")
    return hmac.new(_download_secret(), payload, hashlib.sha256).hexdigest()


@mcp.tool()
def probe_read(message: str = "hello") -> dict:
    """Side-effect-free connectivity probe."""
    return {
        "ok": True,
        "project": PROJECT,
        "version": VERSION,
        "probe": "read",
        "message": message[:500],
        "server_time_utc": _utc_iso(),
    }


@mcp.tool()
def probe_capabilities() -> dict:
    """Describe the current P1 capability boundary."""
    return {
        "project": PROJECT,
        "version": VERSION,
        "transport_target": "MCP Streamable HTTP",
        "endpoint": "/mcp",
        "tools": [
            "probe_read",
            "probe_capabilities",
            "create_document",
            "inspect_document",
            "export_document",
            "delete_document",
        ],
        "p1_scope": [
            "opaque document_id",
            "bounded ephemeral filesystem object store",
            "minimal HWPX materialization via python-hwpx",
            "structural ZIP/XML validation",
            "short-lived signed download URL",
        ],
        "not_in_scope_yet": [
            "existing HWPX upload/ingest",
            "rich editing/formatting",
            "OAuth/per-user identity",
            "persistent cloud object storage",
            "Hancom renderer fidelity oracle",
        ],
    }


@mcp.tool()
def create_document(
    text: str,
    title: str = "",
    filename: str = "document.hwpx",
    access_token: str = "",
) -> dict:
    """Create an ephemeral HWPX document and return an opaque document_id."""
    _require_access_token(access_token)
    _cleanup_expired()

    document_id = _new_document_id()
    hwpx_path, _ = _paths(document_id)
    safe_filename = sanitize_filename(filename)
    validation = materialize_hwpx(hwpx_path, text, title)
    created = time.time()
    expires = created + DOC_TTL_SECONDS
    metadata = {
        "document_id": document_id,
        "filename": safe_filename,
        "title": title[:500],
        "created_at": _utc_iso(created),
        "created_at_epoch": created,
        "expires_at": _utc_iso(expires),
        "expires_at_epoch": expires,
        "sha256": validation["sha256"],
        "bytes": validation["bytes"],
        "storage": "ephemeral-filesystem",
        "format": "hwpx",
    }
    _write_metadata(document_id, metadata)
    return {
        "ok": True,
        **metadata,
        "validation": {"valid": True},
        "next": "Call export_document to obtain a short-lived download URL.",
    }


@mcp.tool()
def inspect_document(document_id: str, access_token: str = "") -> dict:
    """Inspect one P1 document by opaque document_id without exposing server paths."""
    _require_access_token(access_token)
    metadata = _load_metadata(document_id)
    hwpx_path, _ = _paths(document_id)
    validation = validate_hwpx_package(hwpx_path)
    return {
        "ok": True,
        **metadata,
        "validation": validation,
    }


@mcp.tool()
def export_document(
    document_id: str,
    access_token: str = "",
    link_ttl_seconds: int = 300,
) -> dict:
    """Return a short-lived signed HTTPS download URL for an existing P1 document."""
    _require_access_token(access_token)
    metadata = _load_metadata(document_id)
    requested_ttl = max(60, min(int(link_ttl_seconds), 900))
    document_expiry = int(float(metadata["expires_at_epoch"]))
    expires_at = min(int(time.time()) + requested_ttl, document_expiry)
    if expires_at <= int(time.time()):
        raise FileNotFoundError("Document expired")
    signature = _download_signature(document_id, expires_at)
    query = urlencode({"exp": expires_at, "sig": signature})
    download_url = f"{_public_base_url()}/artifacts/{document_id}?{query}"
    return {
        "ok": True,
        "document_id": document_id,
        "filename": metadata["filename"],
        "bytes": metadata["bytes"],
        "sha256": metadata["sha256"],
        "download_url": download_url,
        "download_expires_at": _utc_iso(expires_at),
        "cache_policy": "private, no-store",
    }


@mcp.tool()
def delete_document(document_id: str, access_token: str = "") -> dict:
    """Delete one P1 document and its metadata from the ephemeral object store."""
    _require_access_token(access_token)
    _load_metadata(document_id, allow_expired=True)
    removed = _delete_document_files(document_id)
    return {"ok": True, "document_id": document_id, "deleted": removed}


@mcp.custom_route("/artifacts/{document_id}", methods=["GET"])
async def download_artifact(request):
    document_id = request.path_params.get("document_id", "")
    if not DOC_ID_RE.fullmatch(document_id):
        return PlainTextResponse("Invalid document id", status_code=400)

    try:
        expires_at = int(request.query_params.get("exp", "0"))
    except ValueError:
        return PlainTextResponse("Invalid expiry", status_code=400)
    signature = request.query_params.get("sig", "")

    if expires_at <= int(time.time()):
        return PlainTextResponse("Download link expired", status_code=410)
    expected = _download_signature(document_id, expires_at)
    if not signature or not secrets.compare_digest(signature, expected):
        return PlainTextResponse("Invalid download signature", status_code=403)

    try:
        metadata = _load_metadata(document_id)
        hwpx_path, _ = _paths(document_id)
    except FileNotFoundError:
        return PlainTextResponse("Document not found", status_code=404)

    return FileResponse(
        hwpx_path,
        media_type="application/hwp+zip",
        filename=metadata["filename"],
        headers={"Cache-Control": "private, no-store"},
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    return JSONResponse(
        {
            "status": "ok",
            "project": PROJECT,
            "version": VERSION,
            "phase": "P1",
        }
    )


def _transport_security() -> TransportSecuritySettings:
    public_host = (
        os.environ.get("MCP_PUBLIC_HOST")
        or os.environ.get("RENDER_EXTERNAL_HOSTNAME")
        or ""
    ).strip()

    if public_host:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[public_host, f"{public_host}:*"],
            allowed_origins=[f"https://{public_host}"],
        )

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
        ],
    )


if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("MCP_PORT", "8000")))
    path = os.environ.get("MCP_PATH", "/mcp")
    mcp.run(
        "streamable-http",
        host=host,
        port=port,
        streamable_http_path=path,
        stateless_http=True,
        json_response=True,
        transport_security=_transport_security(),
    )
