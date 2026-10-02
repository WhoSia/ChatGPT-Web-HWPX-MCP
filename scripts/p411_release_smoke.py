from p411_capture_protocol import capture_worker_contract
from p411_release_service import evaluate_release_candidate, release_promotion_contract
from p411_visual_oracle import build_golden_registry, evaluate_visual_slo, load_calibration, load_visual_slo_policy, native_render_oracle_contract

contract=native_render_oracle_contract()
assert contract["phase"]=="P4.11"
assert contract["product"]=="0.36.0-p4.11"
registry=build_golden_registry(load_calibration())
assert registry["case_count"]==8
assert capture_worker_contract()["phase"]=="P4.11"
policy=load_visual_slo_policy()
assert policy["mode"]=="SHADOW_NONBLOCKING"
assert evaluate_visual_slo({"issues":[]},policy=policy)["status"]=="PASS"
assert release_promotion_contract()["product"]=="0.36.0-p4.11"
shadow=evaluate_release_candidate({"exact_head":"a"*40,"static_test_pass":True,"full_lifecycle_pass":True,"exact_head_docker_pass":True,"production_boundary_pass":True,"native_capture_pass":True,"visual_slo_status":"FAIL","novel_unadjudicated":0})
assert shadow["verdict"]=="SERVICE_DEPLOYABLE_VISUAL_AUTHORITY_HOLD"
print("P4.11 continuous native render oracle smoke PASS")
