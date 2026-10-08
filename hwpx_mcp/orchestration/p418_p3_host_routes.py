"""Locked-down browser entrypoint for independently approved P4.18 native edits.

No OAuth bearer tokens, approval keys, signing keys or document lease tokens
are ever exposed to the browser. Disabled unless host-specific secrets exist.
"""
from __future__ import annotations

import html
import json
import re
from urllib.parse import parse_qs, urlsplit

from starlette.responses import HTMLResponse

from hwpx_mcp.orchestration.p418_p2_admission import AdmissionError

_PATH = "/p418/host/review"
_WORKFLOW = re.compile(r"^[A-Za-z0-9_-]{16,96}$")
_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "Referrer-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy":
        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'; style-src 'unsafe-inline'",
}


def _html(body: str, *, status: int = 200):
    return HTMLResponse(
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>HWPX 문서 변경 승인</title>"
        "<style>body{font:16px system-ui,sans-serif;max-width:54rem;"
        "margin:2.5rem auto;padding:0 1.2rem;line-height:1.6}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:1rem;"
        "background:#f2f4f7;border-radius:.5rem}"
        "input,button{font:inherit;padding:.6rem;margin:.4rem 0}"
        "form{margin:1rem 0}button{cursor:pointer}</style>"
        "</head><body><main>" + body + "</main></body></html>",
        status_code=status, headers=_HEADERS,
    )


def _field(s: str) -> str:
    return html.escape(str(s), quote=True)


def render_login(workflow_id: str):
    return _html(
        "<h1>HWPX 변경 내용 확인</h1>"
        "<p>이 화면은 ChatGPT의 승인 요청과 별개의 서버 인증 단계입니다. "
        "승인 전에 실제 수정 내용을 모두 확인합니다.</p>"
        f"<form method='post' action='{_PATH}' autocomplete='off'>"
        "<input type='hidden' name='mode' value='inspect'>"
        f"<input type='hidden' name='workflow_id' value='{_field(workflow_id)}'>"
        "<label>확인용 비밀번호 "
        "<input type='password' name='passphrase' autocomplete='off'"
        " minlength='24' required autofocus></label>"
        "<button type='submit'>변경 내용 보기</button></form>"
    )


def render_review(packet: dict):
    pretty = json.dumps({
        "작업 종류": packet["effect_scope"],
        "원본 문서": packet["source"],
        "참조 문서": packet["references"],
        "원래의 전체 승인 대상 작업": packet["complete_task"],
        "요청된 변경": packet["requested_actions"],
        "보존 조건": packet["preservation"],
        "내부 문서 lease 존재": packet["lease_credential_present"],
        "작업 해시": packet["draft_sha256"],
        "검토 자료 해시": packet["review_packet_sha256"],
    }, ensure_ascii=False, indent=2, allow_nan=False)
    wid = _field(packet["workflow_id"])
    digest = _field(packet["review_packet_sha256"])
    fields = (
        f"<input type='hidden' name='workflow_id' value='{wid}'>"
        f"<input type='hidden' name='review_sha256' value='{digest}'>"
    )
    password = (
        "<label>최종 확인용 비밀번호 "
        "<input type='password' name='passphrase' autocomplete='off'"
        " minlength='24' required></label>"
    )
    return _html(
        "<h1>문서 변경 최종 확인</h1>"
        "<p><strong>아래 내용을 전부 확인하세요.</strong> 이 화면을 보는 것만으로"
        " 문서는 변경되지 않습니다. 최종 승인 시 변경을 한 번 실행합니다.</p>"
        f"<pre>{_field(pretty)}</pre>"
        f"<form method='post' action='{_PATH}' autocomplete='off'>"
        "<input type='hidden' name='mode' value='approve'>"
        f"{fields}{password}"
        "<button type='submit'>확인한 변경 1회 실행</button></form>"
        f"<form method='post' action='{_PATH}' autocomplete='off'>"
        "<input type='hidden' name='mode' value='deny'>"
        f"{fields}{password}"
        "<button type='submit'>변경 취소</button></form>"
    )


def register_host_review_route(core, *, host_factory):
    """Register a human-only custom HTTP route, not an MCP tool."""
    if not callable(host_factory):
        raise RuntimeError("trusted host factory required")

    @core.mcp.custom_route(_PATH, methods=["GET", "POST"])
    async def p418_host_review(request):
        from os import environ
        host_pass = environ.get("P418_HOST_REVIEW_PASSPHRASE", "")
        host_sign = environ.get("P418_HOST_APPROVAL_SIGNING_SECRET", "")
        state_secret = getattr(core, "STATE_SECRET", "")
        if (len(host_pass) < 24 or len(host_sign) < 32 or
            host_pass == host_sign or host_pass == state_secret or
            host_sign == state_secret):
            return _html("<h1>승인 서버가 비활성화되어 있습니다.</h1>", status=503)
        if request.method == "GET":
            wid = request.query_params.get("workflow_id", "")
            if not _WORKFLOW.fullmatch(wid):
                return _html("<h1>유효하지 않은 작업입니다.</h1>", status=400)
            return render_login(wid)
        # A foreign web page cannot silently POST an approval form.
        base = urlsplit(getattr(core, "PUBLIC_BASE_URL", ""))
        expected_origin = f"{base.scheme}://{base.netloc}"
        if not expected_origin.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
            return _html("<h1>서버 origin 구성이 잘못되었습니다.</h1>", status=503)
        received_origin = request.headers.get("origin", "")
        if received_origin:
            # A stated foreign/null Origin always fails, irrespective of Referer.
            same_origin = received_origin == expected_origin
        else:
            # Same-origin HTML form navigation may omit Origin. Fall back only
            # when BOTH the same-origin Referer and browser fetch metadata
            # positively establish a same-origin navigation.
            referer = urlsplit(request.headers.get("referer", ""))
            referer_origin = f"{referer.scheme}://{referer.netloc}"
            same_origin = (
                referer_origin == expected_origin
                and request.headers.get("sec-fetch-site", "") == "same-origin"
                and request.headers.get("sec-fetch-mode", "") == "navigate"
            )
        if not same_origin:
            return _html("<h1>승인 origin 검증 실패</h1>", status=403)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/x-www-form-urlencoded":
            return _html("<h1>지원되지 않는 제출 형식입니다.</h1>", status=415)
        try:
            advertised_length = int(request.headers.get("content-length", "0") or "0")
        except ValueError:
            return _html("<h1>유효하지 않은 요청 크기입니다.</h1>", status=400)
        if advertised_length < 0 or advertised_length > 4096:
            return _html("<h1>요청 크기 제한 초과</h1>", status=413)
        raw = await request.body()
        if len(raw) > 4096:
            return _html("<h1>요청 크기 제한 초과</h1>", status=413)
        form = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
        if any(len(v) != 1 for v in form.values()):
            return _html("<h1>중복 제출값은 허용되지 않습니다.</h1>", status=400)
        wid = form.get("workflow_id", [""])[0]
        mode = form.get("mode", [""])[0]
        password = form.get("passphrase", [""])[0]
        if not _WORKFLOW.fullmatch(wid) or mode not in {"inspect", "approve", "deny"}:
            return _html("<h1>유효하지 않은 승인 요청입니다.</h1>", status=400)
        allowed_fields = (
            {"mode", "workflow_id", "passphrase"}
            if mode == "inspect"
            else {"mode", "workflow_id", "passphrase", "review_sha256"}
        )
        if set(form) != allowed_fields:
            return _html("<h1>확인되지 않은 제출 항목입니다.</h1>", status=400)
        try:
            host = host_factory()
            if mode == "inspect":
                packet = host.inspect(workflow_id=wid, passphrase=password)
                return render_review(packet)
            if mode == "deny":
                host.deny(workflow_id=wid, passphrase=password)
                return _html("<h1>변경 요청이 취소됐습니다.</h1>")
            digest = form.get("review_sha256", [""])[0]
            result = host.approve_and_execute(
                workflow_id=wid, passphrase=password,
                displayed_review_sha256=digest)
            displayed = json.dumps(result, ensure_ascii=False, indent=2)
            return _html("<h1>승인된 변경 실행 결과</h1>"
                         f"<pre>{_field(displayed)}</pre>"
                         "<p>문서의 파일 전달은 인증된 MCP 도구에서 "
                         "문서 ID와 정확한 revision을 지정해 수행하세요.</p>")
        except AdmissionError:
            return _html("<h1>확인 실패 또는 승인 불가</h1>"
                         "<p>인증, 원본 revision 또는 요청 상태를 확인하세요. "
                         "불확실한 변경은 자동으로 재실행되지 않습니다.</p>", status=409)
        except Exception:
            # Never reflect internal state, SQL, signing keys or passphrases.
            return _html("<h1>확인 결과를 보장할 수 없습니다.</h1>"
                         "<p>문서를 다시 변경하지 마세요. 서버의 승인·복구 상태를 "
                         "먼저 확인해야 합니다.</p>", status=503)

    return p418_host_review
