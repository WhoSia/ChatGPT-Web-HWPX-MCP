from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import p348_marketplace as m


def _keys():
    return {name:Ed25519PrivateKey.generate() for name in ["registry","w1","w2","publisher","publisher2"]}


def _policy(keys):
    return {
        "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-trust-policy/v1",
        "registry":m.public_key_record(keys["registry"].public_key(),key_id="registry-1",principal_id="public-registry",principal_field="registry_id"),
        "witnesses":[
            m.public_key_record(keys["w1"].public_key(),key_id="w1-k1",principal_id="witness-a",principal_field="witness_id"),
            m.public_key_record(keys["w2"].public_key(),key_id="w2-k1",principal_id="witness-b",principal_field="witness_id"),
        ],
        "minimum_witnesses":2,
    }


def _publisher(keys,name="publisher",publisher_id="acme",key_id="acme-k1"):
    return m.public_key_record(keys[name].public_key(),key_id=key_id,principal_id=publisher_id,principal_field="publisher_id")


def _claim(keys):
    pub=_publisher(keys)
    return m.sign_marketplace_event({
        "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1",
        "sequence":1,"event_type":"NAMESPACE_CLAIM","timestamp":"2026-09-28T00:00:00Z",
        "namespace":"acme","publisher":pub,"previous_event_sha256":None,
    },keys["publisher"])


def _publish(keys,claim,package_id="sha256:"+"1"*64,version="1.0.0"):
    pub={k:v for k,v in _publisher(keys).items() if k!="public_key_raw_base64"}
    return m.sign_marketplace_event({
        "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1",
        "sequence":2,"event_type":"PUBLISH","timestamp":"2026-09-28T00:01:00Z",
        "namespace":"acme","publisher":pub,"previous_event_sha256":claim["event_sha256"],
        "package":{
            "package_id":package_id,"extension_id":"acme.table","version":version,
            "publisher_certificate_sha256":"c"*64,
            "capabilities":[{"name":"table.inspect","version":"1.0.0","effect":"READ_ONLY"}],
        },
    },keys["publisher"])


def _checkpoint(keys,events,previous=None):
    return m.build_checkpoint(
        events,registry_private_key=keys["registry"],registry_id="public-registry",registry_key_id="registry-1",
        witness_signers=[("witness-a","w1-k1",keys["w1"]),("witness-b","w2-k1",keys["w2"])],
        previous_checkpoint_sha256=previous,created_at="2026-09-28T00:02:00Z",
    )


def test_signed_namespace_publication_snapshot_and_capability_discovery():
    keys=_keys();policy=_policy(keys);claim=_claim(keys);publish=_publish(keys,claim)
    cp=_checkpoint(keys,[claim,publish]);snapshot=m.build_snapshot([claim,publish],cp)
    verified=m.verify_snapshot(snapshot,policy)
    assert verified["state"]["packages"][0]["state"]=="PUBLISHED"
    found=m.discover_candidates(verified["state"],{"required_capabilities":["table.inspect"],"max_effect":"READ_ONLY"})
    assert [x["package_id"] for x in found["candidates"]]==["sha256:"+"1"*64]
    assert found["authority"]=="DISCOVERY_ONLY_NOT_INSTALL_AUTHORITY"


def test_forged_publisher_event_and_namespace_hijack_fail_closed():
    keys=_keys();claim=_claim(keys);publish=_publish(keys,claim)
    forged=copy.deepcopy(publish);forged["verification"]["signature_base64"]="A"*86+"=="
    with pytest.raises(RuntimeError):
        m.verify_event_log([claim,forged])

    attacker=_publisher(keys,"publisher2","attacker","attacker-k1")
    hijack=m.sign_marketplace_event({
        "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1",
        "sequence":2,"event_type":"NAMESPACE_CLAIM","timestamp":"2026-09-28T00:01:00Z",
        "namespace":"acme","publisher":attacker,"previous_event_sha256":claim["event_sha256"],
    },keys["publisher2"])
    with pytest.raises(RuntimeError):
        m.verify_event_log([claim,hijack])


def test_key_rotation_preserves_namespace_continuity_and_old_key_loses_authority():
    keys=_keys();claim=_claim(keys)
    current={k:v for k,v in _publisher(keys).items() if k!="public_key_raw_base64"}
    nxt=_publisher(keys,"publisher2","acme","acme-k2")
    rotate=m.sign_marketplace_event({
        "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1",
        "sequence":2,"event_type":"KEY_ROTATE","timestamp":"2026-09-28T00:01:00Z",
        "namespace":"acme","publisher":current,"next_publisher":nxt,"previous_event_sha256":claim["event_sha256"],
    },keys["publisher"])
    new_pub={k:v for k,v in nxt.items() if k!="public_key_raw_base64"}
    published=m.sign_marketplace_event({
        "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1",
        "sequence":3,"event_type":"PUBLISH","timestamp":"2026-09-28T00:02:00Z",
        "namespace":"acme","publisher":new_pub,"previous_event_sha256":rotate["event_sha256"],
        "package":{"package_id":"sha256:"+"2"*64,"extension_id":"acme.rotate","version":"1.0.0","publisher_certificate_sha256":"d"*64,"capabilities":[]},
    },keys["publisher2"])
    assert m.verify_event_log([claim,rotate,published])["state"]["packages"][0]["state"]=="PUBLISHED"

    old_publish=copy.deepcopy(published)
    old_publish.pop("verification",None);old_publish["publisher"]=current
    old_publish["event_sha256"]=m.normalize_event(old_publish)["event_sha256"]
    old_publish=m.sign_marketplace_event(old_publish,keys["publisher"])
    with pytest.raises(RuntimeError,match="not current namespace owner"):
        m.verify_event_log([claim,rotate,old_publish])


def test_mirror_prefix_and_same_height_split_view_are_distinguished():
    keys=_keys();policy=_policy(keys);claim=_claim(keys);pub1=_publish(keys,claim)
    cp1=_checkpoint(keys,[claim,pub1]);snap1=m.build_snapshot([claim,pub1],cp1)

    pub2=_publish(keys,claim,package_id="sha256:"+"3"*64,version="2.0.0")
    cp2=_checkpoint(keys,[claim,pub2]);snap2=m.build_snapshot([claim,pub2],cp2)
    assert m.compare_snapshots(snap1,snap2,policy)["verdict"]=="EQUIVOCATION"

    owner={k:v for k,v in _publisher(keys).items() if k!="public_key_raw_base64"}
    revoke=m.sign_marketplace_event({
        "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-event/v1",
        "sequence":3,"event_type":"REVOKE","timestamp":"2026-09-28T00:03:00Z",
        "namespace":"acme","publisher":owner,"package_id":pub1["package"]["package_id"],
        "previous_event_sha256":pub1["event_sha256"],"reason":"security incident",
    },keys["publisher"])
    cp3=_checkpoint(keys,[claim,pub1,revoke],previous=cp1["checkpoint_sha256"])
    snap3=m.build_snapshot([claim,pub1,revoke],cp3)
    assert m.compare_snapshots(snap1,snap3,policy)["verdict"]=="CONSISTENT_PREFIX"
    assert m.verify_snapshot(snap3,policy)["state"]["packages"][0]["state"]=="REVOKED"


def test_offline_bundle_is_pinned_to_external_trust_policy_and_rust_verifier_when_built():
    keys=_keys();policy=_policy(keys);claim=_claim(keys);publish=_publish(keys,claim)
    cp=_checkpoint(keys,[claim,publish]);snapshot=m.build_snapshot([claim,publish],cp)
    verifier=shutil.which("p348-marketplace-verifier") or Path("rust/p348_marketplace_verifier/target/release/p348-marketplace-verifier")
    if not Path(str(verifier)).is_file():
        pytest.skip("Rust verifier not built in this environment")
    bundle=m.build_offline_bundle(snapshot,policy,publish["package"]["package_id"])
    verified=m.verify_offline_bundle(bundle,policy)
    assert verified["rust"]["authority"]=="RUST_OFFLINE_MARKETPLACE_BUNDLE_PASS"
    wrong=_policy(_keys())
    with pytest.raises(RuntimeError,match="pinned policy"):
        m.verify_offline_bundle(bundle,wrong)
