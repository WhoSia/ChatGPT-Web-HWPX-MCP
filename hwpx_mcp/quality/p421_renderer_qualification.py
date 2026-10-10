"""P4.21 fail-closed renderer qualification and fresh corpus gate."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def qualification():
    rival=json.loads((ROOT/"benchmarks/p421_renderer_qualification.json").read_text(encoding="utf-8"))
    intake=json.loads((ROOT/"corpus/p421_candidate_intake.json").read_text(encoding="utf-8"))
    registration=json.loads((ROOT/"benchmarks/p421_preregistration.json").read_text(encoding="utf-8"))
    issues=[]
    if not rival["verified"]["checksum_verified"]: issues.append("RIVAL_BINARY_UNVERIFIED")
    if not rival["verified"]["execution_pass"]: issues.append("RIVAL_NOT_EXECUTED")
    if rival["claimed"]["equations"]!="EXACT_VERIFIED": issues.append("EQUATION_REFERENCE_INELIGIBLE")
    if not rival["verified"]["hancom_native_capture"]: issues.append("HANCOM_NATIVE_CAPTURE_MISSING")
    if intake["new_source_bytes_verified"]==0: issues.append("NO_FRESH_SOURCE_BYTES")
    if any(not row["prior_exposure"] for row in intake["prior_sources"]): issues.append("HISTORICAL_SOURCE_MISLABEL")
    if any(row["source_sha256"] is not None for row in registration["cases"]): issues.append("UNAPPROVED_ENROLLMENT")
    result={"status":"HOLD" if issues else "READY_FOR_EXTERNAL_VALIDATION","issues":sorted(issues),"previously_exposed_sources":len(intake["prior_sources"]),"production_release_eligible":False}
    result["receipt_sha256"]=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    return result
