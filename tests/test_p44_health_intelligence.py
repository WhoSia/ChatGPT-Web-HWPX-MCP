from hwpx_mcp.quality.p44_health_intelligence import attribute_feature_families_from_evidence,build_operator_dashboard,build_support_bundle,detect_longitudinal_drift,health_intelligence_contract,route_native_render_escalation
def _r(i,ok=True):return {"phase":f"P4.{i}","product":f"0.{26+i}.0-p4.{i}","exact_head":f"{i:040x}","observed_at":f"2026-09-{20+i:02d}T00:00:00+00:00","python_hwpx":"6.6.0","product_authority_pass":ok,"metrics":{"create_validate_p95_ms":100+i}}
def test_contract():c=health_intelligence_contract();assert c["phase"]=="P4.4" and c["authority_boundary"]["mutation_authority_transferred"] is False
def test_attribution_and_abstention():
 r=attribute_feature_families_from_evidence({"document_sha256":"a"*64,"signals":{"hyperlink":True,"merged_table":True,"table":True}});assert {"HYPERLINKS","MERGED_TABLES"}<={x["family"] for x in r["candidates"]};assert attribute_feature_families_from_evidence({"signals":{}})["abstain"] is True
def test_conservative_drift():
 rows=[_r(i) for i in range(1,5)];assert detect_longitudinal_drift(rows)["calibrated_slo"] is False;bad=detect_longitudinal_drift(rows+[_r(5,False)]);assert bad["status"]=="DRIFT_DETECTED"
def test_native_router():
 assert route_native_render_escalation({"locus":"INDEPENDENT_ORACLE_DIVERGENCE","severity":"LOW"})["route"]=="PARSER_EVIDENCE_CONTINUE";assert route_native_render_escalation({"locus":"INDEPENDENT_ORACLE_DIVERGENCE","severity":"HIGH"})["route"]=="NATIVE_RENDER_REQUIRED";assert route_native_render_escalation({"locus":"PACKAGE_OR_CONTAINER","severity":"CRITICAL"})["route"]=="ENGINEERING_REPRODUCTION"
def test_dashboard_bundle_redaction():
 releases=[_r(1),_r(2)];corpus=[{"source_id":"x","federation_namespace":"repo","feature_family":"HYPERLINKS","source_kind":"TEST","observed_at":"2026-09-29T00:00:00+00:00"}];assert build_operator_dashboard(releases,corpus)["federated_corpus"]["namespace_count"]==1;b=build_support_bundle({"token":"x","message":"ok","raw_stack_trace":"x"},releases,corpus);assert "token" not in b["context"] and "raw_stack_trace" not in b["context"]
