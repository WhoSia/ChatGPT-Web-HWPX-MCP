from __future__ import annotations

import sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from hwpx_mcp.extensions.p348_marketplace import (
    public_key_record,sign_marketplace_event,build_checkpoint,build_snapshot,verify_snapshot,
    discover_candidates,compare_snapshots,build_offline_bundle,verify_offline_bundle,
)

keys={n:Ed25519PrivateKey.generate() for n in ["registry","w1","w2","publisher"]}
policy={
    "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-trust-policy/v1",
    "registry":public_key_record(keys["registry"].public_key(),key_id="reg-k1",principal_id="public-registry",principal_field="registry_id"),
    "witnesses":[
        public_key_record(keys["w1"].public_key(),key_id="w1-k1",principal_id="witness-a",principal_field="witness_id"),
        public_key_record(keys["w2"].public_key(),key_id="w2-k1",principal_id="witness-b",principal_field="witness_id"),
    ],
    "minimum_witnesses":2,
}
publisher=public_key_record(keys["publisher"].public_key(),key_id="pub-k1",principal_id="release-publisher",principal_field="publisher_id")
claim=sign_marketplace_event({
    "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1","sequence":1,"event_type":"NAMESPACE_CLAIM",
    "timestamp":"2026-09-28T00:00:00Z","namespace":"release","publisher":publisher,"previous_event_sha256":None,
},keys["publisher"])
owner={k:v for k,v in publisher.items() if k!="public_key_raw_base64"}
publish=sign_marketplace_event({
    "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1","sequence":2,"event_type":"PUBLISH",
    "timestamp":"2026-09-28T00:01:00Z","namespace":"release","publisher":owner,"previous_event_sha256":claim["event_sha256"],
    "package":{
        "package_id":"sha256:"+"4"*64,"extension_id":"release.table","version":"1.0.0",
        "publisher_certificate_sha256":"5"*64,
        "capabilities":[{"name":"document.table.inspect","version":"1.0.0","effect":"READ_ONLY"}],
    },
},keys["publisher"])
cp=build_checkpoint(
    [claim,publish],registry_private_key=keys["registry"],registry_id="public-registry",registry_key_id="reg-k1",
    witness_signers=[("witness-a","w1-k1",keys["w1"]),("witness-b","w2-k1",keys["w2"])],
    created_at="2026-09-28T00:02:00Z",
)
snapshot=build_snapshot([claim,publish],cp)
verified=verify_snapshot(snapshot,policy)
assert verified["authority"]=="TRANSPARENCY_SNAPSHOT_VERIFIED_PASS"
discovery=discover_candidates(verified["state"],{"required_capabilities":["document.table.inspect"],"max_effect":"READ_ONLY"})
assert discovery["candidate_count"]==1
bundle=build_offline_bundle(snapshot,policy,publish["package"]["package_id"])
assert verify_offline_bundle(bundle,policy)["rust"]["authority"]=="RUST_OFFLINE_MARKETPLACE_BUNDLE_PASS"

revoke=sign_marketplace_event({
    "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1","sequence":3,"event_type":"REVOKE",
    "timestamp":"2026-09-28T00:03:00Z","namespace":"release","publisher":owner,
    "package_id":publish["package"]["package_id"],"previous_event_sha256":publish["event_sha256"],"reason":"release smoke revocation",
},keys["publisher"])
cp2=build_checkpoint(
    [claim,publish,revoke],registry_private_key=keys["registry"],registry_id="public-registry",registry_key_id="reg-k1",
    witness_signers=[("witness-a","w1-k1",keys["w1"]),("witness-b","w2-k1",keys["w2"])],
    previous_checkpoint_sha256=cp["checkpoint_sha256"],created_at="2026-09-28T00:04:00Z",
)
revoked=build_snapshot([claim,publish,revoke],cp2)
assert compare_snapshots(snapshot,revoked,policy)["verdict"]=="CONSISTENT_PREFIX"
assert verify_snapshot(revoked,policy)["state"]["packages"][0]["state"]=="REVOKED"
try:
    build_offline_bundle(revoked,policy,publish["package"]["package_id"])
except RuntimeError:
    pass
else:
    raise AssertionError("revoked package remained offline-admissible")
print("P3.48 release smoke PASS")
