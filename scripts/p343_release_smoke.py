from pathlib import Path
import tempfile
from hwpx import HwpxDocument
from p22_formatting import build_formatting_map
from p334r2_package_validation import validate_hwpx_package_light
from p335_atlas import _sha
from p343_design_system import apply_constraint_preserving_template_migration_atomic, design_system_adaptation_contract

with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/"p343.hwpx";doc=HwpxDocument.new();doc.add_paragraph("기관 제목");doc.add_paragraph("본문");doc.save_to_path(path);doc.close()
    rows=[r for r in build_formatting_map(path)["paragraphs"] if r.get("direct_text_length")];title,body=rows[0]["locator"],rows[1]["locator"]
    template={"schema":"hwpx-template-candidate/v1","source_corpus_sha256":"1"*64,"synthesis_mode":"EXPLICIT_EXEMPLAR",
              "role_presets":{"title":{"run_format":{"font":"Arial","size":15.0},"paragraph_format":{"alignment":"CENTER"}},
                              "body":{"run_format":{"font":"Arial","size":10.5},"paragraph_format":{"alignment":"LEFT"}}},
              "support":{"documents":1},"source_ids":["s"],"source_receipts":{"s":"2"*64},"institutions":["기관A"],
              "dimension_provenance":{},"unresolved_dimensions":[],"compatibility_notes":"release","authority":"EVIDENCE_GUIDED_TEMPLATE_CANDIDATE"}
    template["template_sha256"]=_sha(template);template["template_id"]="tpl_"+template["template_sha256"][:24]
    policy={"organization_id":"org-a","policy_id":"release","hard":{"allowed_fonts":["Arial"],"min_size_pt":9,"max_size_pt":18,"required_roles":["title","body"],"required_literal_text":["기관 제목"]}}
    receipt=apply_constraint_preserving_template_migration_atomic(path,template,{"title":[title],"body":[body]},policy,expected_revision=1,current_revision=1,validator=validate_hwpx_package_light)
    assert receipt["policy_gate"]=="PASS" and design_system_adaptation_contract()["phase"]=="P3.43"
print("P3.43 release smoke PASS")
