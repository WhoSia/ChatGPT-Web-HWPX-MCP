from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlencode
from xml.etree import ElementTree

from hwpx import HwpxDocument
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from auth_store import DurableOAuthStore
from document_store import DurableDocumentStore
from oauth_provider import HWPX_SCOPE, SUBJECT, SingleUserOAuthProvider, build_auth_settings

PROJECT = "ChatGPT Web HWPX MCP"
VERSION = "0.2.2-p1.2"


def _public_base_url() -> str:
    explicit = os.environ.get("P1_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if host:
        return f"https://{host}"
    return "http://127.0.0.1:8000"


PUBLIC_BASE_URL = _public_base_url()
MCP_RESOURCE_URL = f"{PUBLIC_BASE_URL}/mcp"
OAUTH_PASSPHRASE = os.environ.get("P11_OAUTH_PASSPHRASE", "")
AUTH_DATABASE_URL = os.environ.get("P12_AUTH_DATABASE_URL", "")
STATE_SECRET = os.environ.get("P12_STATE_SECRET", "")
DOCUMENT_DATABASE_URL = os.environ.get("P30_DOCUMENT_DATABASE_URL", "").strip() or AUTH_DATABASE_URL
OAUTH_STORE = DurableOAuthStore(AUTH_DATABASE_URL, STATE_SECRET)
DOCUMENT_STORE = DurableDocumentStore(DOCUMENT_DATABASE_URL, STATE_SECRET)
OAUTH_PROVIDER = SingleUserOAuthProvider(
    base_url=PUBLIC_BASE_URL,
    resource_url=MCP_RESOURCE_URL,
    passphrase=OAUTH_PASSPHRASE,
    store=OAUTH_STORE,
)

mcp = MCPServer(
    PROJECT,
    instructions=(
        "P1.2 authenticated HWPX service for ChatGPT Web. OAuth clients, refresh-token families, "
        "and revocation state survive service restarts in an encrypted Postgres store. Tools never "
        "accept passwords or bearer tokens as arguments. Existing HWPX ingress is bounded and validated."
    ),
    auth=build_auth_settings(base_url=PUBLIC_BASE_URL, resource_url=MCP_RESOURCE_URL),
    auth_server_provider=OAUTH_PROVIDER,
)

OBJECT_DIR = Path(os.environ.get("P1_OBJECT_DIR", "/tmp/chatgpt-web-hwpx-mcp-p1"))
OBJECT_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_SECRET = os.environ.get("P1_DOWNLOAD_SECRET", "")
DOC_TTL_SECONDS = max(
    3600,
    min(
        int(
            os.environ.get(
                "P30_DOC_RETENTION_SECONDS",
                os.environ.get("P1_DOC_TTL_SECONDS", "604800"),
            )
        ),
        2_592_000,
    ),
)
MAX_TEXT_CHARS = max(1000, min(int(os.environ.get("P1_MAX_TEXT_CHARS", "100000")), 500000))
MAX_PACKAGE_BYTES = 8_000_000
MAX_INGEST_BYTES = 2_000_000
MAX_ZIP_ENTRIES = 512
MAX_EXPANDED_BYTES = 32_000_000
MAX_ENTRY_BYTES = 8_000_000
MAX_COMPRESSION_RATIO = 100.0
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


def _caller_subject() -> str:
    token = get_access_token()
    if token is None:
        raise PermissionError("Authenticated MCP request required")
    if HWPX_SCOPE not in token.scopes:
        raise PermissionError("Missing hwpx scope")
    if token.subject != SUBJECT:
        raise PermissionError("Unknown resource owner")
    return token.subject


def _require_owner(metadata: dict) -> str:
    subject = _caller_subject()
    if metadata.get("owner_subject") != subject:
        raise PermissionError("Document is not owned by the authenticated principal")
    return subject


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


def _hydrate_local(document_id: str, durable: dict) -> dict:
    hwpx_path, metadata_path = _paths(document_id)
    metadata = dict(durable["metadata"])
    metadata["revision"] = int(durable["revision"])
    metadata["sha256"] = durable["sha256"]
    metadata["bytes"] = len(durable["bytes"])
    metadata["storage"] = DOCUMENT_STORE.mode
    hwpx_path.write_bytes(durable["bytes"])
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata


def _write_metadata(document_id: str, metadata: dict) -> None:
    hwpx_path, metadata_path = _paths(document_id)
    if not hwpx_path.is_file():
        raise FileNotFoundError("Document bytes missing before durable commit")
    metadata = dict(metadata)
    metadata["storage"] = DOCUMENT_STORE.mode
    metadata.setdefault("revision", 1)
    raw = hwpx_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    metadata["sha256"] = digest
    metadata["bytes"] = len(raw)
    try:
        DOCUMENT_STORE.put_revision(
            document_id=document_id,
            owner_subject=str(metadata["owner_subject"]),
            revision=int(metadata["revision"]),
            metadata=metadata,
            data=raw,
            expires_at_epoch=float(metadata["expires_at_epoch"]),
        )
    except Exception:
        durable = DOCUMENT_STORE.load_current(document_id, allow_expired=True)
        if durable is None:
            for path in (hwpx_path, metadata_path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        else:
            _hydrate_local(document_id, durable)
        raise
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_metadata(document_id: str, *, allow_expired: bool = False) -> dict:
    hwpx_path, metadata_path = _paths(document_id)
    durable = DOCUMENT_STORE.load_current(document_id, allow_expired=allow_expired)
    if durable is None:
        raise FileNotFoundError("Unknown document_id")

    needs_hydration = True
    if hwpx_path.is_file() and metadata_path.is_file():
        try:
            local = json.loads(metadata_path.read_text(encoding="utf-8"))
            local_revision = int(local.get("revision", 1))
            local_sha = hashlib.sha256(hwpx_path.read_bytes()).hexdigest()
            needs_hydration = not (
                local_revision == int(durable["revision"])
                and local_sha == durable["sha256"]
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            needs_hydration = True

    metadata = _hydrate_local(document_id, durable) if needs_hydration else json.loads(
        metadata_path.read_text(encoding="utf-8")
    )
    if not allow_expired and float(metadata["expires_at_epoch"]) <= time.time():
        _delete_document_files(document_id)
        raise FileNotFoundError("Document expired")
    return metadata


def _delete_document_files(document_id: str) -> bool:
    hwpx_path, metadata_path = _paths(document_id)
    removed = DOCUMENT_STORE.delete_document(document_id)
    for path in (hwpx_path, metadata_path):
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed


def _cleanup_expired() -> None:
    DOCUMENT_STORE.cleanup_expired()
    now = time.time()
    for metadata_path in OBJECT_DIR.glob("doc_*.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if float(metadata.get("expires_at_epoch", 0)) <= now:
                document_id = metadata_path.stem
                if DOC_ID_RE.fullmatch(document_id):
                    hwpx_path, _ = _paths(document_id)
                    for path in (hwpx_path, metadata_path):
                        try:
                            path.unlink()
                        except FileNotFoundError:
                            pass
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue


def _safe_zip_name(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def validate_hwpx_package(path: Path, *, ingress: bool = False) -> dict:
    package_bytes = path.stat().st_size
    if package_bytes > MAX_PACKAGE_BYTES:
        raise ValueError(f"HWPX package exceeds {MAX_PACKAGE_BYTES} bytes")
    if ingress and package_bytes > MAX_INGEST_BYTES:
        raise ValueError(f"Existing-HWPX ingress exceeds {MAX_INGEST_BYTES} bytes")

    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if not infos:
            raise ValueError("Empty HWPX package")
        if len(infos) > MAX_ZIP_ENTRIES:
            raise ValueError("HWPX package contains too many ZIP entries")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entry names are not allowed")
        if any(not _safe_zip_name(name) for name in names):
            raise ValueError("Unsafe ZIP entry path")
        if any(info.flag_bits & 0x1 for info in infos):
            raise ValueError("Encrypted ZIP entries are not allowed")
        if infos[0].filename != "mimetype":
            raise ValueError("HWPX mimetype must be the first ZIP entry")
        if infos[0].compress_type != zipfile.ZIP_STORED:
            raise ValueError("HWPX mimetype must be stored without compression")

        expanded = 0
        for info in infos:
            if info.file_size > MAX_ENTRY_BYTES:
                raise ValueError(f"ZIP entry is too large: {info.filename}")
            expanded += info.file_size
            if expanded > MAX_EXPANDED_BYTES:
                raise ValueError("Expanded HWPX package is too large")
            if info.file_size > 1_000_000 and info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_COMPRESSION_RATIO:
                    raise ValueError(f"Suspicious ZIP compression ratio: {info.filename}")

        missing = sorted(REQUIRED_HWPX_ENTRIES - set(names))
        if missing:
            raise ValueError(f"Missing required HWPX entries: {', '.join(missing)}")
        if archive.read("mimetype") != b"application/hwp+zip":
            raise ValueError("Invalid HWPX mimetype signature")
        bad_crc = archive.testzip()
        if bad_crc is not None:
            raise ValueError(f"CRC failure in ZIP entry: {bad_crc}")

        parsed_xml = 0
        for info in infos:
            lower = info.filename.lower()
            if not (lower.endswith(".xml") or lower.endswith(".hpf")):
                continue
            payload = archive.read(info.filename)
            upper = payload.upper()
            if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
                raise ValueError(f"DTD/entity declarations are not allowed: {info.filename}")
            ElementTree.fromstring(payload)
            parsed_xml += 1

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "valid": True,
        "sha256": digest,
        "bytes": package_bytes,
        "zip_entries": len(infos),
        "expanded_bytes": expanded,
        "parsed_xml_entries": parsed_xml,
        "required_entries": sorted(REQUIRED_HWPX_ENTRIES),
        "ingress_profile": "bounded-existing-hwpx" if ingress else "generated-hwpx",
    }


def materialize_hwpx(path: Path, text: str, title: str = "") -> dict:
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"text exceeds P1_MAX_TEXT_CHARS={MAX_TEXT_CHARS}")
    if not text.strip() and not title.strip():
        raise ValueError("Document must contain title or text")
    document = HwpxDocument.new()
    if title.strip():
        document.add_paragraph(title.strip())
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        document.add_paragraph(paragraph)
    document.save_to_path(str(path))
    return validate_hwpx_package(path)


def _metadata(document_id: str, *, filename: str, owner_subject: str, validation: dict, title: str = "", source: str) -> dict:
    created = time.time()
    expires = created + DOC_TTL_SECONDS
    return {
        "document_id": document_id,
        "filename": filename,
        "title": title[:500],
        "owner_subject": owner_subject,
        "created_at": _utc_iso(created),
        "created_at_epoch": created,
        "expires_at": _utc_iso(expires),
        "expires_at_epoch": expires,
        "sha256": validation["sha256"],
        "bytes": validation["bytes"],
        "storage": DOCUMENT_STORE.mode,
        "format": "hwpx",
        "source": source,
    }


def _download_signature(document_id: str, expires_at: int) -> str:
    payload = f"{document_id}:{expires_at}".encode("utf-8")
    return hmac.new(_download_secret(), payload, hashlib.sha256).hexdigest()


@mcp.tool()
def probe_read(message: str = "hello") -> dict:
    subject = _caller_subject()
    return {
        "ok": True,
        "project": PROJECT,
        "version": VERSION,
        "probe": "read",
        "message": message[:500],
        "authenticated_subject": subject,
        "server_time_utc": _utc_iso(),
    }


@mcp.tool()
def probe_capabilities() -> dict:
    subject = _caller_subject()
    return {
        "project": PROJECT,
        "version": VERSION,
        "authenticated_subject": subject,
        "transport_target": "OAuth-protected MCP Streamable HTTP",
        "oauth_state_store": OAUTH_PROVIDER.state_store_mode,
        "endpoint": "/mcp",
        "tools": [
            "probe_read",
            "probe_capabilities",
            "create_document",
            "ingest_document",
            "inspect_document",
            "export_document",
            "delete_document",
        ],
        "p12_scope": [
            "durable encrypted OAuth client/token state",
            "restart-safe DCR and refresh-token authority",
            "refresh-token rotation and family revocation",
            "secret-free MCP tool schemas",
            "authenticated document ownership",
            "bounded existing-HWPX base64 ingress",
            "ZIP path/size/ratio/encryption/duplicate/CRC checks",
            "DTD/entity rejection and XML parse checks",
            "opaque document_id and short-lived signed export",
        ],
        "not_in_scope_yet": [
            "durable document object storage",
            "large-file streaming ingress",
            "rich editing/formatting",
            "Hancom renderer fidelity oracle",
        ],
    }


@mcp.tool()
def create_document(text: str, title: str = "", filename: str = "document.hwpx") -> dict:
    owner_subject = _caller_subject()
    _cleanup_expired()
    document_id = _new_document_id()
    hwpx_path, _ = _paths(document_id)
    safe_filename = sanitize_filename(filename)
    validation = materialize_hwpx(hwpx_path, text, title)
    metadata = _metadata(
        document_id,
        filename=safe_filename,
        owner_subject=owner_subject,
        validation=validation,
        title=title,
        source="generated",
    )
    _write_metadata(document_id, metadata)
    return {"ok": True, **metadata, "validation": validation, "next": "Call export_document for a signed download URL."}


@mcp.tool()
def ingest_document(content_base64: str, filename: str = "existing.hwpx") -> dict:
    """Admit one small existing HWPX after bounded package and XML validation."""
    owner_subject = _caller_subject()
    _cleanup_expired()
    if len(content_base64) > ((MAX_INGEST_BYTES + 2) // 3) * 4 + 16:
        raise ValueError("Encoded HWPX exceeds the P1.2 ingress limit")
    try:
        payload = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("content_base64 is not valid base64") from exc
    if len(payload) > MAX_INGEST_BYTES:
        raise ValueError(f"Existing-HWPX ingress exceeds {MAX_INGEST_BYTES} bytes")
    if payload[:2] != b"PK":
        raise ValueError("Existing-HWPX ingress is not a ZIP package")

    document_id = _new_document_id()
    hwpx_path, _ = _paths(document_id)
    try:
        hwpx_path.write_bytes(payload)
        validation = validate_hwpx_package(hwpx_path, ingress=True)
        metadata = _metadata(
            document_id,
            filename=sanitize_filename(filename),
            owner_subject=owner_subject,
            validation=validation,
            source="existing-ingress",
        )
        _write_metadata(document_id, metadata)
    except Exception:
        _delete_document_files(document_id)
        raise
    return {"ok": True, **metadata, "validation": validation, "admission": "PASS"}


@mcp.tool()
def inspect_document(document_id: str) -> dict:
    metadata = _load_metadata(document_id)
    _require_owner(metadata)
    hwpx_path, _ = _paths(document_id)
    validation = validate_hwpx_package(hwpx_path, ingress=metadata.get("source") == "existing-ingress")
    return {"ok": True, **metadata, "validation": validation}


@mcp.tool()
def export_document(document_id: str, link_ttl_seconds: int = 300) -> dict:
    metadata = _load_metadata(document_id)
    _require_owner(metadata)
    requested_ttl = max(60, min(int(link_ttl_seconds), 900))
    document_expiry = int(float(metadata["expires_at_epoch"]))
    expires_at = min(int(time.time()) + requested_ttl, document_expiry)
    if expires_at <= int(time.time()):
        raise FileNotFoundError("Document expired")
    signature = _download_signature(document_id, expires_at)
    query = urlencode({"exp": expires_at, "sig": signature})
    return {
        "ok": True,
        "document_id": document_id,
        "filename": metadata["filename"],
        "bytes": metadata["bytes"],
        "sha256": metadata["sha256"],
        "download_url": f"{PUBLIC_BASE_URL}/artifacts/{document_id}?{query}",
        "download_expires_at": _utc_iso(expires_at),
        "cache_policy": "private, no-store",
    }


@mcp.tool()
def delete_document(document_id: str) -> dict:
    metadata = _load_metadata(document_id, allow_expired=True)
    _require_owner(metadata)
    removed = _delete_document_files(document_id)
    return {"ok": True, "document_id": document_id, "deleted": removed}


@mcp.custom_route("/oauth/approve", methods=["GET", "POST"])
async def oauth_approve(request):
    headers = {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }
    if request.method == "GET":
        request_id = request.query_params.get("request", "")
        status = OAUTH_PROVIDER.approval_status(request_id)
        if status == "missing":
            return HTMLResponse("<h1>Authorization request expired</h1><p>Return to ChatGPT and reconnect the app.</p>", status_code=410, headers=headers)
        if status == "unconfigured":
            return HTMLResponse("<h1>OAuth not configured</h1><p>Set P11_OAUTH_PASSPHRASE on the server, then reconnect.</p>", status_code=503, headers=headers)
        safe_request = html.escape(request_id, quote=True)
        body = f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Authorize HWPX MCP</title></head><body><main><h1>Authorize ChatGPT Web HWPX MCP</h1><p>This grants the current ChatGPT MCP client permission to create, ingest, inspect, export, and delete bounded HWPX documents.</p><form method=\"post\" action=\"/oauth/approve\" autocomplete=\"off\"><input type=\"hidden\" name=\"request\" value=\"{safe_request}\"><label>Authorization passphrase <input type=\"password\" name=\"passphrase\" required minlength=\"12\" autofocus></label><button type=\"submit\" name=\"decision\" value=\"approve\">Authorize</button><button type=\"submit\" name=\"decision\" value=\"deny\">Deny</button></form></main></body></html>"""
        return HTMLResponse(body, headers=headers)

    body = (await request.body()).decode("utf-8", errors="replace")
    form = parse_qs(body, keep_blank_values=True)
    request_id = form.get("request", [""])[0]
    decision = form.get("decision", ["approve"])[0]
    if decision == "deny":
        redirect = OAUTH_PROVIDER.deny(request_id)
        if redirect is None:
            return HTMLResponse("<h1>Authorization request expired</h1>", status_code=410, headers=headers)
        return RedirectResponse(redirect, status_code=303, headers=headers)
    supplied = form.get("passphrase", [""])[0]
    ok, result = OAUTH_PROVIDER.approve(request_id, supplied)
    if not ok:
        return HTMLResponse(f"<h1>Authorization failed</h1><p>{html.escape(result)}</p><p>Return to ChatGPT and retry authorization.</p>", status_code=401, headers=headers)
    return RedirectResponse(result, status_code=303, headers=headers)


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
    return FileResponse(hwpx_path, media_type="application/hwp+zip", filename=metadata["filename"], headers={"Cache-Control": "private, no-store"})


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    try:
        oauth_counts = OAUTH_STORE.counts()
        db_ok = True
    except Exception:
        oauth_counts = {}
        db_ok = False
    return JSONResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "project": PROJECT,
            "version": VERSION,
            "phase": "P1.2",
            "oauth": {
                "enabled": True,
                "configured": OAUTH_PROVIDER.configured,
                "resource": MCP_RESOURCE_URL,
                "scope": HWPX_SCOPE,
                "state_store": OAUTH_PROVIDER.state_store_mode,
                "durable_store_reachable": db_ok,
                "active_state_counts": oauth_counts,
            },
            "ingress": {
                "enabled": True,
                "max_bytes": MAX_INGEST_BYTES,
                "transport": "base64-tool-argument",
            },
        },
        status_code=200 if db_ok else 503,
    )


def _transport_security() -> TransportSecuritySettings:
    public_host = (os.environ.get("MCP_PUBLIC_HOST") or os.environ.get("RENDER_EXTERNAL_HOSTNAME") or "").strip()
    if public_host:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[public_host, f"{public_host}:*"],
            allowed_origins=[f"https://{public_host}"],
        )
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
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
