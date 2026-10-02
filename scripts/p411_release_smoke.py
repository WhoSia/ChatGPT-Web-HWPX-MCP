from p411_capture_protocol import capture_worker_contract
from p411_visual_oracle import build_golden_registry, load_calibration, native_render_oracle_contract

contract=native_render_oracle_contract()
assert contract["phase"]=="P4.11"
assert contract["product"]=="0.36.0-p4.11"
registry=build_golden_registry(load_calibration())
assert registry["case_count"]==8
assert capture_worker_contract()["phase"]=="P4.11"
print("P4.11 continuous native render oracle smoke PASS")
