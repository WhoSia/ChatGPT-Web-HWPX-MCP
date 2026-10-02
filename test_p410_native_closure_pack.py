from pathlib import Path

from scripts.p410_materialize_native_closure_pack import run


def test_p410_native_closure_pack_contains_both_evidence_families(tmp_path: Path):
    result = run(tmp_path)
    assert result["phase"] == "P4.10"
    assert result["product"] == "0.35.0-p4.10"
    assert result["archetype_count"] == 5
    assert result["equation_witness_count"] == 3
    assert (tmp_path / "sources" / "archetypes" / "p48-lab_report.hwpx").exists()
    assert (tmp_path / "sources" / "equations" / "p49-lpile-alignment-witness.hwpx").exists()
    assert (tmp_path / "capture" / "p410_run_hancom_capture.ps1").exists()
    assert (tmp_path / "review" / "p410-human-visual-adjudication-template.json").exists()
    assert (tmp_path / "review" / "p410-closure-evidence-template.json").exists()
    assert (tmp_path / "README-NATIVE-CAPTURE.txt").exists()
