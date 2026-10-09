from __future__ import annotations

import pytest
import p348_mcp


class _MCP:
    def __init__(self): self.tools={}
    def tool(self,*,annotations=None):
        def deco(fn): self.tools[fn.__name__]=fn;return fn
        return deco


class _Core:
    def __init__(self): self.mcp=_MCP()
    @staticmethod
    def _caller_subject(): return "pytest"


class _Registry:
    def __init__(self): self.calls=[];self.promoted="sha256:"+"1"*64
    def install(self,package,**kwargs):
        self.calls.append(("install",package,kwargs))
        return {"generation":4,"installed_package_id":self.promoted,"certificate":{"status":"PASS"}}
    def snapshot(self,document_id):
        return {"generation":7,"promoted_by_extension":{"acme.table":self.promoted}}
    def rollback(self,extension_id,**kwargs):
        self.calls.append(("rollback",extension_id,kwargs))
        return {"restored_package_id":"sha256:"+"0"*64,"generation":8}
    def advance(self,package_id,target_state,**kwargs):
        self.calls.append(("advance",package_id,target_state,kwargs))
        return {"generation":8,"package_id":package_id,"to_state":target_state}


def test_marketplace_registration_and_install_delegates_final_authority_to_p347(monkeypatch):
    core=_Core();registry=_Registry();owned={"doc":({"revision":1},object())}
    pkg=registry.promoted
    monkeypatch.setattr(p348_mcp,"marketplace_contract",lambda:{"phase":"P3.48"})
    monkeypatch.setattr(p348_mcp,"verify_offline_bundle",lambda b,p:{"package_id":pkg,"snapshot_sha256":"a"*64})
    monkeypatch.setattr(p348_mcp,"normalize_extension_package",lambda p:{"package_id":pkg})
    p348_mcp.register_p348_tools(core,lambda d:owned[d],registry)
    names=set(core.mcp.tools)
    assert {"get_extension_marketplace_contract","verify_extension_marketplace_snapshot","discover_extension_marketplace","compare_extension_marketplace_mirrors","verify_extension_marketplace_bundle","install_marketplace_extension","reconcile_revoked_marketplace_extension"}<=names
    out=core.mcp.tools["install_marketplace_extension"]("doc",{}, {}, {"x":1},{},[],3,[])
    assert out["authority"]=="MARKETPLACE_VERIFIED_P347_INSTALL_TIME_RECERTIFICATION_PASS"
    assert registry.calls[0][0]=="install"
    with pytest.raises(KeyError):
        core.mcp.tools["install_marketplace_extension"]("missing",{}, {}, {"x":1},{},[],3,[])


def test_revoke_reconciler_rolls_back_promoted_revoked_package(monkeypatch):
    core=_Core();registry=_Registry();owned={"doc":({"revision":1},object())}
    monkeypatch.setattr(p348_mcp,"verify_snapshot",lambda s,p:{"snapshot_sha256":"b"*64,"state":{"packages":[{"package_id":registry.promoted,"state":"REVOKED"}]}})
    p348_mcp.register_p348_tools(core,lambda d:owned[d],registry)
    out=core.mcp.tools["reconcile_revoked_marketplace_extension"]("doc",{}, {},"acme.table",7)
    assert out["action"]=="ROLLBACK"
    assert out["authority"]=="REVOKED_PACKAGE_EXACT_CERTIFIED_ROLLBACK_PASS"
    assert registry.calls[-1][0]=="rollback"


def test_revoke_without_prior_promotion_retires_instead_of_leaving_revoked_code_promoted(monkeypatch):
    core=_Core();registry=_Registry();owned={"doc":({"revision":1},object())}
    monkeypatch.setattr(p348_mcp,"verify_snapshot",lambda s,p:{"snapshot_sha256":"b"*64,"state":{"packages":[{"package_id":registry.promoted,"state":"REVOKED"}]}})
    def no_history(*args,**kwargs): raise RuntimeError("P3.47 rollback history has no prior promoted package")
    registry.rollback=no_history
    p348_mcp.register_p348_tools(core,lambda d:owned[d],registry)
    out=core.mcp.tools["reconcile_revoked_marketplace_extension"]("doc",{}, {},"acme.table",7)
    assert out["action"]=="RETIRE"
    assert out["authority"]=="REVOKED_PACKAGE_RETIRED_NO_SAFE_ROLLBACK_TARGET"
