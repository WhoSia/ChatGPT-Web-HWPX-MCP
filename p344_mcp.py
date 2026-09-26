from __future__ import annotations

from typing import Any, Callable, Mapping

from p344_autonomous_authoring import (
    append_event,
    autonomous_authoring_contract,
    diagnostic_summary,
    evaluate_runtime_gate,
    human_feedback_verdict,
    new_run,
    normalize_config,
    repair_plan_summary,
    verify_run,
)


def register_p344_tools(
    core,
    *,
    compile_rich_plan: Callable[[dict], dict],
    create_document_from_plan: Callable[..., dict],
    diagnose_rendered: Callable[..., dict],
    plan_repairs: Callable[..., dict],
    apply_repairs: Callable[..., dict],
    delivery_after_commit: Callable[..., Any],
):
    def _persist(run: dict) -> None:
        metadata = core._load_metadata(run["document_id"])
        core._require_owner(metadata)
        metadata["p344_autonomous_run"] = run
        core._write_metadata(run["document_id"], metadata)

    def _stored(document_id: str) -> tuple[dict, dict]:
        metadata = core._load_metadata(document_id)
        core._require_owner(metadata)
        run = metadata.get("p344_autonomous_run")
        if not isinstance(run, dict):
            raise FileNotFoundError("P3.44 autonomous run not found")
        return metadata, verify_run(run)

    def _policy_ok(policy_receipt: Mapping[str, Any] | None) -> bool:
        if policy_receipt is None:
            return True
        return str(policy_receipt.get("policy_gate") or "").upper() == "PASS"

    def _design_mode(archetype: str) -> str:
        value = str(archetype or "POLISHED_REPORT").upper()
        return (
            "INSTITUTIONAL_COMPATIBILITY"
            if value in {"INSTITUTIONAL_REPORT", "FORM"}
            else "POLISHED_REPORT"
        )

    def _static_cycle(run: dict, *, archetype: str, auto_repair: bool) -> tuple[dict, dict]:
        while True:
            diagnostic = diagnose_rendered(
                run["document_id"],
                mode=_design_mode(archetype),
                capture=None,
                renderer=None,
                render_observation=None,
                human_feedback=None,
            )
            repair_plan = plan_repairs(
                run["document_id"],
                mode=_design_mode(archetype),
                archetype=archetype,
                capture=None,
                renderer=None,
                render_observation=None,
                human_feedback=None,
            )
            ds = diagnostic_summary(diagnostic)
            rs = repair_plan_summary(repair_plan)
            snapshot = {
                "static_verdict": ds["verdict"],
                "render_requirement": run["config"]["render_requirement"],
                "render_verdict": "NOT_PROVIDED",
                "repairable": rs["repairable"],
                "repairs_used": run["repair_rounds"],
                "max_repairs": run["config"]["max_repair_rounds"],
                "policy_ok": run["policy_ok"],
                "footprint_ok": run["footprint_ok"],
                "human_requirement": run["config"]["human_requirement"],
                "human_verdict": "PENDING",
            }
            gate = evaluate_runtime_gate(snapshot)
            run = append_event(
                run,
                stage="STATIC_CRITIQUE",
                revision=int(diagnostic["revision"]),
                evidence={
                    "diagnostic": ds,
                    "repair_plan": rs,
                    "gate": gate,
                },
            )
            run["latest_static"] = ds
            run["latest_repair_plan"] = rs
            run["latest_gate"] = gate
            run["status"] = gate["action"]
            run["next_action"] = gate["action"]

            if gate["action"] != "REPAIR" or not auto_repair:
                from p344_autonomous_authoring import _seal_run
                run = _seal_run(run)
                return run, repair_plan

            repair = apply_repairs(
                run["document_id"],
                expected_revision=int(diagnostic["revision"]),
                repair_plan=repair_plan,
                lease_token="",
            )
            tx = repair.get("design_repair") or {}
            enforcement = tx.get("preservation_enforcement") or {}
            run["footprint_ok"] = bool(enforcement.get("passed", False))
            run["repair_rounds"] = int(run["repair_rounds"]) + 1
            run = append_event(
                run,
                stage="REPAIR",
                revision=int(repair["revision_after"]),
                evidence={
                    "repair_plan_sha256": rs.get("repair_plan_sha256"),
                    "p342_receipt_sha256": tx.get("p342_receipt_sha256"),
                    "preservation_grade": (tx.get("mutation_footprint") or {}).get("preservation", {}).get("actual_grade"),
                    "preservation_passed": bool(enforcement.get("passed", False)),
                },
            )

    @core.mcp.tool()
    def get_autonomous_authoring_contract() -> dict:
        """Return the bounded P3.44 autonomous authoring state-machine and evidence contract."""
        core._caller_subject()
        return {"ok": True, **autonomous_authoring_contract()}

    @core.mcp.tool()
    def get_autonomous_authoring_run(document_id: str) -> dict:
        """Return one persisted P3.44 run receipt for an owned document."""
        core._caller_subject()
        metadata, run = _stored(document_id)
        return {"ok": True, "document_id": document_id, "revision": int(metadata["revision"]), "run": run}

    @core.mcp.tool()
    def start_autonomous_professional_authoring(
        rich_plan: dict,
        filename: str = "document.hwpx",
        request_id: str = "",
        archetype: str = "POLISHED_REPORT",
        config: dict | None = None,
        organization_policy_receipt: dict | None = None,
    ):
        """Plan, compose, statically critique and bounded-repair a professional HWPX, pausing for required world contact."""
        core._caller_subject()
        cfg = normalize_config(config)
        compiled = compile_rich_plan(rich_plan)
        created = create_document_from_plan(
            compiled["plan"],
            filename,
            "",
            str(request_id or ""),
        )
        run = new_run(
            document_id=created["document_id"],
            revision=int(created.get("revision", 1)),
            plan_sha256=str(compiled.get("plan_sha256") or compiled.get("rich_plan_sha256") or created.get("composition_plan_sha256") or ""),
            archetype=archetype,
            config=cfg,
            policy_ok=_policy_ok(organization_policy_receipt),
        )
        run, _ = _static_cycle(run, archetype=str(archetype).upper(), auto_repair=bool(cfg["auto_repair"]))
        _persist(run)

        if run["next_action"] == "DELIVER" and cfg["delivery_when_ready"]:
            return delivery_after_commit(
                run["document_id"],
                int(run["revision"]),
                int(cfg["link_ttl_seconds"]),
                "P344_AUTONOMOUS_PLAN_COMPOSE_CRITIQUE_REPAIR_DELIVER",
                extra={"phase": "P3.44", "autonomous_run": run},
            )
        return {
            "ok": run["next_action"] not in {"HOLD"},
            "document_id": run["document_id"],
            "revision": int(run["revision"]),
            "run": run,
            "next": (
                "Provide Hancom/native render evidence with resume_autonomous_professional_authoring."
                if run["next_action"] == "WAIT_RENDER"
                else run["next_action"]
            ),
        }

    @core.mcp.tool()
    def resume_autonomous_professional_authoring(
        document_id: str,
        run_sha256: str,
        capture: dict | None = None,
        renderer: dict | None = None,
        render_observation: dict | None = None,
        human_feedback: list[dict] | None = None,
        deliver_if_ready: bool = True,
    ):
        """Resume a P3.44 run from render/human evidence; any repair invalidates the old render and requires re-render."""
        core._caller_subject()
        metadata, run = _stored(document_id)
        if str(run_sha256 or "") != str(run["run_sha256"]):
            raise ValueError("STALE_P344_RUN_RECEIPT")
        if int(metadata["revision"]) != int(run["revision"]):
            raise ValueError("P3.44 document revision changed outside the run")

        diagnostic = diagnose_rendered(
            document_id,
            mode=_design_mode(run["archetype"]),
            capture=capture,
            renderer=renderer,
            render_observation=render_observation,
            human_feedback=human_feedback,
        )
        repair_plan = plan_repairs(
            document_id,
            mode=_design_mode(run["archetype"]),
            archetype=run["archetype"],
            capture=capture,
            renderer=renderer,
            render_observation=render_observation,
            human_feedback=human_feedback,
        )
        ds = diagnostic_summary(diagnostic)
        rs = repair_plan_summary(repair_plan)
        render_verdict = ds["verdict"] if (capture is not None or render_observation is not None) else "NOT_PROVIDED"
        human_verdict = human_feedback_verdict(human_feedback)
        snapshot = {
            "static_verdict": run.get("latest_static", {}).get("verdict", "PASS_WITH_WARNINGS"),
            "render_requirement": run["config"]["render_requirement"],
            "render_verdict": render_verdict,
            "repairable": rs["repairable"],
            "repairs_used": run["repair_rounds"],
            "max_repairs": run["config"]["max_repair_rounds"],
            "policy_ok": run["policy_ok"],
            "footprint_ok": run["footprint_ok"],
            "human_requirement": run["config"]["human_requirement"],
            "human_verdict": human_verdict,
        }
        gate = evaluate_runtime_gate(snapshot)
        run["render_cycle"] = int(run.get("render_cycle", 0)) + (1 if render_verdict != "NOT_PROVIDED" else 0)
        run = append_event(
            run,
            stage="RENDER_CRITIQUE" if render_verdict != "NOT_PROVIDED" else "HUMAN_REVIEW",
            revision=int(metadata["revision"]),
            evidence={"diagnostic": ds, "repair_plan": rs, "gate": gate, "human_verdict": human_verdict},
        )
        run["latest_render"] = ds if render_verdict != "NOT_PROVIDED" else run.get("latest_render")
        run["latest_repair_plan"] = rs
        run["latest_gate"] = gate

        if gate["action"] == "REPAIR" and run["config"]["auto_repair"]:
            repair = apply_repairs(
                document_id,
                expected_revision=int(metadata["revision"]),
                repair_plan=repair_plan,
                lease_token="",
            )
            tx = repair.get("design_repair") or {}
            enforcement = tx.get("preservation_enforcement") or {}
            run["footprint_ok"] = bool(enforcement.get("passed", False))
            run["repair_rounds"] = int(run["repair_rounds"]) + 1
            run = append_event(
                run,
                stage="REPAIR_AFTER_RENDER",
                revision=int(repair["revision_after"]),
                evidence={
                    "p342_receipt_sha256": tx.get("p342_receipt_sha256"),
                    "preservation_grade": (tx.get("mutation_footprint") or {}).get("preservation", {}).get("actual_grade"),
                    "preservation_passed": bool(enforcement.get("passed", False)),
                    "previous_render_invalidated": True,
                },
            )
            run["status"] = "WAIT_RENDER"
            run["next_action"] = "WAIT_RENDER"
            run["latest_gate"] = {
                "action": "WAIT_RENDER",
                "reason": "RE_RENDER_REQUIRED_AFTER_REPAIR",
                "authority": gate["authority"],
            }
            from p344_autonomous_authoring import _seal_run
            run = _seal_run(run)
            _persist(run)
            return {
                "ok": True,
                "document_id": document_id,
                "revision": int(run["revision"]),
                "run": run,
                "next": "Re-render the repaired revision and resume with fresh render evidence.",
            }

        run["status"] = gate["action"]
        run["next_action"] = gate["action"]
        from p344_autonomous_authoring import _seal_run
        run = _seal_run(run)
        _persist(run)
        if gate["action"] == "DELIVER" and bool(deliver_if_ready) and run["config"]["delivery_when_ready"]:
            return delivery_after_commit(
                document_id,
                int(run["revision"]),
                int(run["config"]["link_ttl_seconds"]),
                "P344_AUTONOMOUS_RENDER_CRITIQUE_REPAIR_DELIVER",
                extra={"phase": "P3.44", "autonomous_run": run},
            )
        return {
            "ok": gate["action"] != "HOLD",
            "document_id": document_id,
            "revision": int(run["revision"]),
            "run": run,
            "next": gate["action"],
        }

    return {"phase": "P3.44", "contract": autonomous_authoring_contract()}
