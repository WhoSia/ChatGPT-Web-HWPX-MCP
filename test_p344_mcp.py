from __future__ import annotations

from pathlib import Path

from p344_mcp import register_p344_tools


class MCP:
    def __init__(self):
        self.tools = {}
    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


class Core:
    def __init__(self):
        self.mcp = MCP()
        self.meta = {}
    def _caller_subject(self):
        return "owner"
    def _load_metadata(self, document_id):
        return dict(self.meta[document_id])
    def _require_owner(self, metadata):
        return None
    def _write_metadata(self, document_id, metadata):
        self.meta[document_id] = dict(metadata)


def test_p344_register_start_wait_render_resume_deliver():
    core=Core()
    def compile_rich(plan):
        return {"plan":{"preset":"default","blocks":[]},"plan_sha256":"a"*64}
    def create(plan,filename,template,request):
        core.meta["doc_a"]={"revision":1}
        return {"document_id":"doc_a","revision":1,"composition_plan_sha256":"a"*64}
    def diagnose(document_id,**kwargs):
        render_supplied=kwargs.get("capture") is not None or kwargs.get("render_observation") is not None
        return {
            "revision":core.meta[document_id]["revision"],
            "verdict":"PASS",
            "findings":[],
            "diagnostic_sha256":("c" if render_supplied else "b")*64,
        }
    def plan(document_id,**kwargs):
        return {"repair_plan_sha256":"d"*64,"actions":[]}
    def apply(*args,**kwargs):
        raise AssertionError("clean fixture must not repair")
    delivered={}
    def deliver(document_id,revision,ttl,workflow,extra=None):
        delivered.update({"document_id":document_id,"revision":revision,"workflow":workflow,"extra":extra})
        return {"delivery":"PASS","document_id":document_id,"revision":revision}

    register_p344_tools(
        core,compile_rich_plan=compile_rich,create_document_from_plan=create,
        diagnose_rendered=diagnose,plan_repairs=plan,apply_repairs=apply,
        delivery_after_commit=deliver,
    )
    start=core.mcp.tools["start_autonomous_professional_authoring"](
        {"sections":[{"blocks":[]}]},config={"render_requirement":"REQUIRED"}
    )
    assert start["run"]["next_action"]=="WAIT_RENDER"
    run=start["run"]
    resumed=core.mcp.tools["resume_autonomous_professional_authoring"](
        "doc_a",run["run_sha256"],render_observation={"authority":"TEST","findings":[]}
    )
    assert resumed["delivery"]=="PASS"
    assert delivered["workflow"]=="P344_AUTONOMOUS_RENDER_CRITIQUE_REPAIR_DELIVER"
