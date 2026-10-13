"""Negative controls for P4.21 independent renderer and source claims."""
import json
from hwpx_mcp.quality.p421_renderer_qualification import ROOT,qualification

def test_rival_must_not_promote_upstream_readme():
    x=qualification()
    assert x["status"]=="HOLD"
    assert "RIVAL_BINARY_UNVERIFIED" in x["issues"]
    assert "EQUATION_REFERENCE_INELIGIBLE" in x["issues"]
    assert x["production_release_eligible"] is False

def test_historical_fixtures_are_not_fresh_pilot():
    x=qualification()
    assert x["previously_exposed_sources"]==8
    assert "NO_FRESH_SOURCE_BYTES" in x["issues"]
    p=json.loads((ROOT/"benchmarks/p421_preregistration.json").read_text())
    assert all(c["source_sha256"] is None for c in p["cases"])

def test_binary_execution_not_falsely_claimed():
    q=json.loads((ROOT/"benchmarks/p421_renderer_qualification.json").read_text())
    assert q["verified"]["execution_pass"] is False
    assert q["verified"]["hancom_native_capture"] is False
