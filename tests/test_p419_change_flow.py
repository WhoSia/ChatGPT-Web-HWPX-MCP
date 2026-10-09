from types import SimpleNamespace

import pytest

from p419_change_flow import stage_title_change


DOCUMENT_ID = "doc_test-123456789012"


def _core(*, revision=2, expires=8000):
    return SimpleNamespace(
        PUBLIC_BASE_URL="https://example.org",
        _load_metadata=lambda doc: {
            "revision": revision, "sha256": "a" * 64,
            "expires_at_epoch": expires,
        },
        _require_owner=lambda meta: "hwpx-owner",
    )


def _host_secrets(monkeypatch):
    monkeypatch.setenv("P418_HOST_REVIEW_PASSPHRASE", "p" * 35)
    monkeypatch.setenv("P418_HOST_APPROVAL_SIGNING_SECRET", "s" * 48)


def test_one_call_stages_canonical_draft_with_no_mutation(monkeypatch):
    _host_secrets(monkeypatch)
    witnessed = []

    def stage(draft, preview):
        witnessed.append((draft, preview))
        assert draft["mutation_count"] == 1
        assert draft["executable"] is False
        assert preview["execution_allowed"] is False
        assert draft["steps"][0]["task"]["intent"]["actions"] == [{
            "action": "replace_role_text", "role": "TITLE", "text": "Revised title"
        }]
        return {"ok": True, "state": "STAGED", "workflow_id": "w" * 32,
                "expires_at": "future",
                "human_review_url": "https://example.org/p418/host/review?workflow_id=" + "w" * 32}

    result = stage_title_change(
        _core(), document_id=DOCUMENT_ID, expected_revision=2,
        new_title="Revised title", stage_adapter=stage, now=1000,
    )
    assert result["state"] == "STAGED"
    assert result["mutation_executed"] is False
    assert result["approval_granted"] is False
    assert result["source_sha256"] == "a" * 64
    assert len(witnessed) == 1


def test_mismatch_expiry_and_bad_title_never_stage(monkeypatch):
    _host_secrets(monkeypatch)

    def cannot_stage(*args):
        pytest.fail("must not stage invalid input")

    with pytest.raises(ValueError, match="revision"):
        stage_title_change(_core(), document_id=DOCUMENT_ID, expected_revision=1,
                           new_title="Title", stage_adapter=cannot_stage, now=1000)
    with pytest.raises(ValueError, match="expires too soon"):
        stage_title_change(_core(expires=1200), document_id=DOCUMENT_ID,
                           expected_revision=2, new_title="Title",
                           stage_adapter=cannot_stage, now=1000)
    with pytest.raises(ValueError, match="one nonempty line"):
        stage_title_change(_core(), document_id=DOCUMENT_ID,
                           expected_revision=2, new_title="bad\nline",
                           stage_adapter=cannot_stage, now=1000)


def test_host_unavailable_and_foreign_owner_fail_closed(monkeypatch):
    monkeypatch.delenv("P418_HOST_REVIEW_PASSPHRASE", raising=False)
    monkeypatch.delenv("P418_HOST_APPROVAL_SIGNING_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="host is unavailable"):
        stage_title_change(_core(), document_id=DOCUMENT_ID, expected_revision=2,
                           new_title="Title", stage_adapter=lambda *x: None, now=1000)
    _host_secrets(monkeypatch)
    core = _core()
    core._require_owner = lambda meta: (_ for _ in ()).throw(PermissionError("foreign owner"))
    with pytest.raises(PermissionError, match="foreign owner"):
        stage_title_change(core, document_id=DOCUMENT_ID, expected_revision=2,
                           new_title="Title", stage_adapter=lambda *x: None, now=1000)


def test_unavailable_stage_is_not_reported_as_approved(monkeypatch):
    _host_secrets(monkeypatch)
    with pytest.raises(RuntimeError, match="stage was not available"):
        stage_title_change(_core(), document_id=DOCUMENT_ID, expected_revision=2,
                           new_title="Title", stage_adapter=lambda *x: {
                               "ok": True, "state": "STAGED",
                               "human_review_url": None,
                           }, now=1000)
