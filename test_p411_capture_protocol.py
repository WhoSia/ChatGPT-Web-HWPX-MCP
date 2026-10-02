from p411_capture_protocol import capture_worker_contract, validate_capture_receipt, validate_capture_request

def test_p411_capture_request_contract():
    c=capture_worker_contract()
    assert "exact_head" in c["request_fields"]
    req={
        "job_id":"j1","exact_head":"a"*40,"source_manifest_sha256":"b"*64,
        "source_dir":"C:/src","output_dir":"C:/out","hancom_version_expected":"13.0.0.3622",
        "capture_kind":"archetype"
    }
    assert validate_capture_request(req)["status"]=="PASS"

def test_p411_receipt_never_allows_cleanup_of_preexisting_pid():
    receipt={
        "baseline_hwp_pids":[10],
        "owned_hwp_pids":[20],
        "forced_cleanup_pids":[10],
        "fail_count":0,
        "capture_manifest_sha256":"a"*64,
    }
    result=validate_capture_receipt(receipt)
    assert result["status"]=="FAIL"
    assert any(x["code"]=="FORCED_CLEANUP_NOT_OWNED" for x in result["issues"])
