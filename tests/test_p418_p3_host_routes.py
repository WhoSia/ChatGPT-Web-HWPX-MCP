import asyncio
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from hwpx_mcp.orchestration.p418_p3_host_routes import (
    register_host_review_route, render_review,
)

WID = "test-workflow-abcdef012345"


class FakeMCP:
    def custom_route(self, path, *, methods):
        assert path == "/p418/host/review"
        assert methods == ["GET", "POST"]
        return lambda callback: callback


class FakeRequest:
    def __init__(self, method="GET", data=None, *, origin="https://example.org"):
        self.method = method
        self.query_params = {"workflow_id": WID}
        self._raw = urlencode(data or {}).encode()
        self.headers = {
            "origin": origin,
            "content-type": "application/x-www-form-urlencoded",
            "content-length": str(len(self._raw)),
        }

    async def body(self):
        return self._raw


class StubHost:
    def __init__(self):
        self.calls = []

    def inspect(self, *, workflow_id, passphrase):
        self.calls.append(("inspect", workflow_id, passphrase))
        return sample_packet()

    def approve_and_execute(self, *, workflow_id, passphrase, displayed_review_sha256):
        self.calls.append(("approve", workflow_id, passphrase, displayed_review_sha256))
        return {"state": "COMMITTED", "document_id": "doc1",
                "committed_revision": 4, "mutation_executed": True}

    def deny(self, *, workflow_id, passphrase):
        self.calls.append(("deny", workflow_id, passphrase))
        return {"state": "ABORTED"}


def sample_packet():
    return {
        "workflow_id": WID, "effect_scope": "EDIT_INTENT",
        "source": {"document_id": "doc1", "expected_revision": 3,
                   "source_sha256": "a" * 64},
        "references": [],
        "complete_task": {"kind": "EDIT_INTENT",
                          "intent": {"actions": [{"text": "<script>alert(1)</script>"}]}},
        "requested_actions": [{"text": "<script>alert(1)</script>"}],
        "preservation": {"required_grade": "TARGETED_PARTS_ONLY"},
        "lease_credential_present": True,
        "draft_sha256": "b" * 64,
        "review_packet_sha256": "c" * 64,
    }


def setup(monkeypatch, *, configured=True):
    monkeypatch.setenv("P418_HOST_REVIEW_PASSPHRASE", "p" * 35 if configured else "")
    monkeypatch.setenv("P418_HOST_APPROVAL_SIGNING_SECRET", "k" * 48 if configured else "")
    core = SimpleNamespace(mcp=FakeMCP(),
                           PUBLIC_BASE_URL="https://example.org",
                           STATE_SECRET="s" * 48)
    host = StubHost()
    route = register_host_review_route(core, host_factory=lambda: host)
    return route, host


def test_review_escapes_all_untrusted_text_and_has_no_bearer_credentials():
    body = render_review(sample_packet()).body.decode()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<script>alert(1)</script>" not in body
    assert "lease_token" not in body
    assert "approval_key" not in body
    assert "p418/host/review" in body


def test_disabled_host_and_foreign_origin_are_rejected(monkeypatch):
    route, host = setup(monkeypatch, configured=False)
    page = asyncio.run(route(FakeRequest()))
    assert page.status_code == 503
    assert host.calls == []
    route, host = setup(monkeypatch)
    page = asyncio.run(route(FakeRequest("POST",
        {"mode": "approve", "workflow_id": WID,
         "passphrase": "p" * 35, "review_sha256": "c" * 64},
        origin="https://attacker.example")))
    assert page.status_code == 403
    assert host.calls == []


def test_read_only_inspect_then_explicit_approval(monkeypatch):
    route, host = setup(monkeypatch)
    login = asyncio.run(route(FakeRequest()))
    assert login.status_code == 200
    assert "변경 내용 보기" in login.body.decode()
    assert host.calls == []
    inspect = asyncio.run(route(FakeRequest("POST", {
        "mode": "inspect", "workflow_id": WID, "passphrase": "p" * 35})))
    assert inspect.status_code == 200
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in inspect.body.decode()
    assert len(host.calls) == 1 and host.calls[0][0] == "inspect"
    approved = asyncio.run(route(FakeRequest("POST", {
        "mode": "approve", "workflow_id": WID, "passphrase": "p" * 35,
        "review_sha256": "c" * 64})))
    assert approved.status_code == 200
    assert "COMMITTED" in approved.body.decode()
    assert host.calls[1][0] == "approve"


def test_duplicate_form_keys_and_wrong_content_type_fail_closed(monkeypatch):
    route, host = setup(monkeypatch)
    request = FakeRequest("POST", {"mode": "approve", "workflow_id": WID, "passphrase": "p" * 35})
    request._raw = b"mode=inspect&mode=approve&workflow_id=" + WID.encode()
    request.headers["content-length"] = str(len(request._raw))
    response = asyncio.run(route(request))
    assert response.status_code == 400
    wrong = FakeRequest("POST", {"mode": "inspect", "workflow_id": WID})
    wrong.headers["content-type"] = "application/json"
    assert asyncio.run(route(wrong)).status_code == 415
    assert host.calls == []


def test_missing_origin_requires_same_origin_referer_and_fetch_metadata(monkeypatch):
    route, host = setup(monkeypatch)
    fields = {"mode": "inspect", "workflow_id": WID, "passphrase": "p" * 35}
    same = FakeRequest("POST", fields, origin="")
    same.headers["referer"] = "https://example.org/p418/host/review?workflow_id=" + WID
    same.headers["sec-fetch-site"] = "same-origin"
    same.headers["sec-fetch-mode"] = "navigate"
    response = asyncio.run(route(same))
    assert response.status_code == 200
    assert host.calls[0][0] == "inspect"

    for missing in ("referer", "sec-fetch-site", "sec-fetch-mode"):
        request = FakeRequest("POST", fields, origin="")
        request.headers.update(same.headers)
        request.headers.pop(missing)
        assert asyncio.run(route(request)).status_code == 403

    spoofed = FakeRequest("POST", fields, origin="https://attacker.example")
    spoofed.headers.update({k: v for k, v in same.headers.items() if k != "origin"})
    assert asyncio.run(route(spoofed)).status_code == 403

    foreign = FakeRequest("POST", fields, origin="")
    foreign.headers["referer"] = "https://attacker.example/path"
    foreign.headers["sec-fetch-site"] = "cross-site"
    foreign.headers["sec-fetch-mode"] = "navigate"
    assert asyncio.run(route(foreign)).status_code == 403
    assert len(host.calls) == 1
