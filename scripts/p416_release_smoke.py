from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx_mcp.evidence.p416_generation_manifest import (
    PARENT_RELEASE_AUTHORITY_SHA256,
    classify_reproduction,
    compile_generation_manifest_for_file,
    verify_generation_manifest,
    witness_ablation,
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="p416-smoke-") as td:
        path = Path(td) / "artifact.hwpx"
        path.write_bytes(b"PK\x03\x04p416-smoke")
        manifest = compile_generation_manifest_for_file(
            path,
            intent={"title": "P4.16 smoke"},
            plan={"lane": "smoke"},
            capability_path=["AUTHORING", "DELIVER"],
            tool_trace=[
                {
                    "tool": "smoke_author",
                    "capability": "AUTHORING",
                    "operation": {"id": 1},
                }
            ],
            source_inputs=[],
            runtime_components={"runtime": "smoke"},
            deterministic_parameters={"mode": "SMOKE"},
            release={
                "product": "0.41.0-p4.16",
                "exact_head": "1" * 40,
                "authority_sha256": PARENT_RELEASE_AUTHORITY_SHA256,
                "authority_scope": "SMOKE",
            },
        )
        verified = verify_generation_manifest(
            manifest,
            artifact_sha256=manifest["artifact_sha256"],
        )
        assert verified["status"] == "PASS"

        tampered = json.loads(json.dumps(manifest))
        tampered["artifact_sha256"] = "b" * 64
        assert verify_generation_manifest(tampered)["status"] == "FAIL"

        assert witness_ablation(manifest)["status"] == "PASS"
        assert classify_reproduction(manifest, manifest)["verdict"] == "BYTE_REPRODUCED"

        print(
            json.dumps(
                {
                    "phase": "P4.16",
                    "manifest": "PASS",
                    "offline_verifier": "PASS",
                    "tamper_negative": "PASS",
                    "witness_ablation": "PASS",
                    "reproduction": "BYTE_REPRODUCED",
                    "native_pass_inferred": False,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
