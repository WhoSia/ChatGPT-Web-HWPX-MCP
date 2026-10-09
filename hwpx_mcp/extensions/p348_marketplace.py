from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ROOT=Path(__file__).resolve().parent
_POLICY_SCHEMA="chatgpt-web-hwpx-mcp/p3.48/marketplace-trust-policy/v1"
_SNAPSHOT_SCHEMA="chatgpt-web-hwpx-mcp/p3.48/marketplace-snapshot/v1"
_BUNDLE_SCHEMA="chatgpt-web-hwpx-mcp/p3.48/offline-marketplace-bundle/v1"


def _stable(value: Any) -> str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _sha_bytes(value: bytes) -> bytes:
    return hashlib.sha256(value).digest()


def _raw_public(key: Ed25519PublicKey) -> bytes:
    from cryptography.hazmat.primitives import serialization
    return key.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)


def public_key_record(key: Ed25519PublicKey, *, key_id: str, principal_id: str, principal_field: str) -> dict:
    raw=_raw_public(key)
    return {
        principal_field:str(principal_id),
        "key_id":str(key_id),
        "public_key_raw_base64":base64.b64encode(raw).decode("ascii"),
        "public_key_sha256":hashlib.sha256(raw).hexdigest(),
    }


def _load_raw_public(raw_b64: str) -> Ed25519PublicKey:
    try:
        raw=base64.b64decode(str(raw_b64),validate=True)
        if len(raw)!=32:
            raise ValueError("wrong length")
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception as exc:
        raise RuntimeError("P3.48 Ed25519 public key is invalid") from exc


def _node_bin() -> str:
    explicit=str(os.environ.get("P348_NODE_BIN") or "").strip()
    if explicit:
        return explicit
    found=shutil.which("node") or shutil.which("nodejs")
    if not found:
        raise RuntimeError("P3.48 TypeScript marketplace kernel requires Node.js")
    return found


def _runtime_script() -> Path:
    explicit=str(os.environ.get("P348_TS_RUNTIME") or "").strip()
    candidates=[
        Path(explicit) if explicit else None,
        ROOT/"runtime"/"scripts"/"p348_marketplace_cli.js",
        ROOT/".tmp"/"p348-ts"/"scripts"/"p348_marketplace_cli.js",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("P3.48 compiled TypeScript marketplace kernel is unavailable")


def _runtime(command: str, payload: Mapping[str, Any] | None=None, *, timeout: float=6.0) -> dict:
    proc=subprocess.run(
        [_node_bin(),"--max-old-space-size=64",str(_runtime_script()),command],
        input="" if payload is None else _stable(payload),
        text=True,capture_output=True,timeout=timeout,check=False,
        env={"PATH":os.environ.get("PATH",""),"NODE_NO_WARNINGS":"1","LANG":os.environ.get("LANG","C.UTF-8")},
    )
    if proc.returncode!=0:
        raise RuntimeError("P3.48 TypeScript marketplace kernel failed: "+(proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"))
    try:
        out=json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("P3.48 TypeScript marketplace kernel emitted invalid JSON") from exc
    if not isinstance(out,dict):
        raise RuntimeError("P3.48 TypeScript marketplace result must be object")
    return out


def _verifier_bin() -> str:
    explicit=str(os.environ.get("P348_VERIFIER_BIN") or "").strip()
    if explicit:
        return explicit
    found=shutil.which("p348-marketplace-verifier")
    if found:
        return found
    candidate=ROOT/"rust"/"p348_marketplace_verifier"/"target"/"release"/"p348-marketplace-verifier"
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError("P3.48 Rust marketplace verifier is unavailable")


def _rust(command: str, payload: Mapping[str, Any]) -> dict:
    proc=subprocess.run([_verifier_bin(),command],input=_stable(payload),text=True,capture_output=True,timeout=5.0,check=False)
    if proc.returncode!=0:
        raise RuntimeError("P3.48 Rust marketplace verifier failed: "+(proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"))
    out=json.loads(proc.stdout)
    if not isinstance(out,dict):
        raise RuntimeError("P3.48 Rust verifier result must be object")
    return out


def marketplace_contract() -> dict:
    return _runtime("contract")


def normalize_event(event: Mapping[str, Any]) -> dict:
    return _runtime("event",{"event":dict(event)})


def reduce_events(events: Sequence[Mapping[str, Any]]) -> dict:
    return _runtime("reduce",{"events":[dict(x) for x in events]})


def discover_candidates(state: Mapping[str, Any], request: Mapping[str, Any] | None=None) -> dict:
    return _runtime("discover",{"state":dict(state),"request":dict(request or {})})


def normalize_marketplace_trust_policy(raw: Mapping[str, Any]) -> dict:
    policy=dict(raw or {})
    if policy.get("schema")!=_POLICY_SCHEMA:
        raise ValueError("invalid P3.48 marketplace trust policy schema")
    def norm(row: Mapping[str, Any], principal_field: str) -> dict:
        principal=str((row or {}).get(principal_field) or "")
        key_id=str((row or {}).get("key_id") or "")
        raw_b64=str((row or {}).get("public_key_raw_base64") or "")
        if not principal or not key_id:
            raise ValueError("invalid P3.48 marketplace trust root identity")
        key=_load_raw_public(raw_b64)
        raw_key=_raw_public(key)
        fp=hashlib.sha256(raw_key).hexdigest()
        declared=str((row or {}).get("public_key_sha256") or "")
        if declared and declared!=fp:
            raise ValueError("P3.48 marketplace trust root fingerprint mismatch")
        return {
            principal_field:principal,
            "key_id":key_id,
            "public_key_raw_base64":base64.b64encode(raw_key).decode("ascii"),
            "public_key_sha256":fp,
        }
    registry=norm(dict(policy.get("registry") or {}),"registry_id")
    witnesses=[norm(dict(x or {}),"witness_id") for x in list(policy.get("witnesses") or [])]
    if len(witnesses)<2 or len(witnesses)>32:
        raise ValueError("P3.48 marketplace trust policy requires 2..32 witnesses")
    if len({x["witness_id"] for x in witnesses})!=len(witnesses):
        raise ValueError("duplicate P3.48 witness identity")
    if len({x["public_key_sha256"] for x in witnesses+[registry]})!=len(witnesses)+1:
        raise ValueError("P3.48 registry and witnesses require distinct keys")
    minimum=int(policy.get("minimum_witnesses",2))
    if minimum<2 or minimum>len(witnesses):
        raise ValueError("invalid P3.48 witness quorum")
    body={
        "schema":_POLICY_SCHEMA,
        "registry":registry,
        "witnesses":sorted(witnesses,key=lambda x:(x["witness_id"],x["key_id"])),
        "minimum_witnesses":minimum,
    }
    return {**body,"trust_policy_sha256":_sha(body)}


def sign_marketplace_event(event: Mapping[str, Any], private_key: Ed25519PrivateKey) -> dict:
    normalized=normalize_event(event)
    signature=private_key.sign(_stable(normalized).encode("utf-8"))
    return {
        **normalized,
        "verification":{
            "algorithm":"ed25519",
            "key_id":normalized["publisher"]["key_id"],
            "signature_base64":base64.b64encode(signature).decode("ascii"),
        },
    }


def verify_event_log(events: Sequence[Mapping[str, Any]]) -> dict:
    owners: dict[str,dict]={}
    normalized_rows=[]
    for raw in events:
        normalized=normalize_event(raw)
        ns=normalized["namespace"]
        kind=normalized["event_type"]
        if kind=="NAMESPACE_CLAIM":
            if ns in owners:
                raise RuntimeError("P3.48 namespace was already claimed")
            pub=dict(normalized["publisher"])
            raw_b64=str(pub.get("public_key_raw_base64") or "")
            key=_load_raw_public(raw_b64)
            fp=hashlib.sha256(_raw_public(key)).hexdigest()
            if fp!=pub["public_key_sha256"]:
                raise RuntimeError("P3.48 namespace claim public key fingerprint mismatch")
        else:
            if ns not in owners:
                raise RuntimeError("P3.48 event references unclaimed namespace")
            pub=owners[ns]
            if any(str(normalized["publisher"].get(k))!=str(pub.get(k)) for k in ("publisher_id","key_id","public_key_sha256")):
                raise RuntimeError("P3.48 event signer is not current namespace owner")
            key=_load_raw_public(pub["public_key_raw_base64"])
        verification=dict((raw or {}).get("verification") or {})
        if verification.get("algorithm")!="ed25519" or str(verification.get("key_id") or "")!=str(pub["key_id"]):
            raise RuntimeError("P3.48 event verification key mismatch")
        try:
            sig=base64.b64decode(str(verification.get("signature_base64") or ""),validate=True)
            key.verify(sig,_stable(normalized).encode("utf-8"))
        except Exception as exc:
            raise RuntimeError("P3.48 publisher event signature verification failed") from exc
        normalized_rows.append(normalized)
        if kind=="NAMESPACE_CLAIM":
            owners[ns]={**pub,"generation":1}
        elif kind in {"KEY_ROTATE","OWNER_TRANSFER"}:
            nxt=dict(normalized["next_publisher"])
            next_key=_load_raw_public(nxt["public_key_raw_base64"])
            fp=hashlib.sha256(_raw_public(next_key)).hexdigest()
            if fp!=nxt["public_key_sha256"]:
                raise RuntimeError("P3.48 next publisher public key fingerprint mismatch")
            owners[ns]={**nxt,"generation":int(owners[ns].get("generation",1))+1}
    state=reduce_events(normalized_rows)
    return {
        "events":normalized_rows,
        "state":state,
        "publisher_signature_count":len(normalized_rows),
        "namespace_count":len(owners),
        "authority":"PUBLISHER_SIGNATURE_CONTINUITY_PASS",
    }


def merkle_root(event_hashes: Sequence[str]) -> str:
    if not event_hashes:
        return hashlib.sha256(b"").hexdigest()
    level=[_sha_bytes(b"\x00"+bytes.fromhex(str(x))) for x in event_hashes]
    while len(level)>1:
        nxt=[]
        for i in range(0,len(level),2):
            left=level[i]
            right=level[i+1] if i+1<len(level) else left
            nxt.append(_sha_bytes(b"\x01"+left+right))
        level=nxt
    return level[0].hex()


def _sign_body(body: Mapping[str, Any], private_key: Ed25519PrivateKey, *, key_id: str, principal_id: str, principal_field: str) -> dict:
    sig=private_key.sign(_stable(body).encode("utf-8"))
    return {
        principal_field:str(principal_id),
        "key_id":str(key_id),
        "algorithm":"ed25519",
        "signature_base64":base64.b64encode(sig).decode("ascii"),
    }


def build_checkpoint(
    events: Sequence[Mapping[str, Any]],
    *,
    registry_private_key: Ed25519PrivateKey,
    registry_id: str,
    registry_key_id: str,
    witness_signers: Sequence[tuple[str,str,Ed25519PrivateKey]],
    previous_checkpoint_sha256: str | None=None,
    created_at: str="2026-09-28T00:00:00Z",
) -> dict:
    verified=verify_event_log(events)
    normalized=verified["events"]
    hashes=[x["event_sha256"] for x in normalized]
    body={
        "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-checkpoint-body/v1",
        "epoch":len(normalized),
        "event_count":len(normalized),
        "last_event_sha256":hashes[-1],
        "merkle_root":merkle_root(hashes),
        "state_sha256":verified["state"]["state_sha256"],
        "previous_checkpoint_sha256":previous_checkpoint_sha256,
        "created_at":created_at,
    }
    registry_signature=_sign_body(body,registry_private_key,key_id=registry_key_id,principal_id=registry_id,principal_field="registry_id")
    witness_signatures=sorted(
        [_sign_body(body,key,key_id=key_id,principal_id=witness_id,principal_field="witness_id") for witness_id,key_id,key in witness_signers],
        key=lambda x:(x["witness_id"],x["key_id"]),
    )
    unsigned={
        "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-checkpoint/v1",
        "body":body,
        "registry_signature":registry_signature,
        "witness_signatures":witness_signatures,
    }
    return {**unsigned,"checkpoint_sha256":_sha(unsigned)}


def verify_checkpoint(checkpoint: Mapping[str, Any], trust_policy: Mapping[str, Any]) -> dict:
    policy=normalize_marketplace_trust_policy(trust_policy)
    cp=dict(checkpoint or {})
    if cp.get("schema")!="chatgpt-web-hwpx-mcp/p3.48/marketplace-checkpoint/v1":
        raise RuntimeError("invalid P3.48 marketplace checkpoint schema")
    body=dict(cp.get("body") or {})
    registry_sig=dict(cp.get("registry_signature") or {})
    registry=policy["registry"]
    if registry_sig.get("registry_id")!=registry["registry_id"] or registry_sig.get("key_id")!=registry["key_id"]:
        raise RuntimeError("P3.48 registry checkpoint signer mismatch")
    try:
        sig=base64.b64decode(str(registry_sig.get("signature_base64") or ""),validate=True)
        _load_raw_public(registry["public_key_raw_base64"]).verify(sig,_stable(body).encode("utf-8"))
    except Exception as exc:
        raise RuntimeError("P3.48 registry checkpoint signature failed") from exc
    witnesses_by={(x["witness_id"],x["key_id"]):x for x in policy["witnesses"]}
    accepted=[]
    seen=set()
    for row in list(cp.get("witness_signatures") or []):
        key=(str((row or {}).get("witness_id") or ""),str((row or {}).get("key_id") or ""))
        if key in seen or key not in witnesses_by:
            continue
        if (row or {}).get("algorithm")!="ed25519":
            continue
        root=witnesses_by[key]
        try:
            sig=base64.b64decode(str((row or {}).get("signature_base64") or ""),validate=True)
            _load_raw_public(root["public_key_raw_base64"]).verify(sig,_stable(body).encode("utf-8"))
        except Exception:
            continue
        seen.add(key);accepted.append({"witness_id":key[0],"key_id":key[1]})
    if len(accepted)<policy["minimum_witnesses"]:
        raise RuntimeError("P3.48 checkpoint witness quorum not met")
    unsigned={
        "schema":"chatgpt-web-hwpx-mcp/p3.48/marketplace-checkpoint/v1",
        "body":body,
        "registry_signature":registry_sig,
        "witness_signatures":sorted(list(cp.get("witness_signatures") or []),key=lambda x:(str((x or {}).get("witness_id") or ""),str((x or {}).get("key_id") or ""))),
    }
    observed=str(cp.get("checkpoint_sha256") or "")
    if observed!=_sha(unsigned):
        raise RuntimeError("P3.48 checkpoint seal mismatch")
    return {
        "checkpoint_sha256":observed,
        "accepted_witnesses":accepted,
        "witness_quorum":len(accepted),
        "trust_policy_sha256":policy["trust_policy_sha256"],
        "authority":"REGISTRY_AND_WITNESS_CHECKPOINT_PASS",
    }


def build_snapshot(events: Sequence[Mapping[str, Any]], checkpoint: Mapping[str, Any]) -> dict:
    return {"schema":_SNAPSHOT_SCHEMA,"events":[copy.deepcopy(dict(x)) for x in events],"checkpoint":copy.deepcopy(dict(checkpoint))}


def verify_snapshot(snapshot: Mapping[str, Any], trust_policy: Mapping[str, Any]) -> dict:
    snap=dict(snapshot or {})
    if snap.get("schema")!=_SNAPSHOT_SCHEMA:
        raise RuntimeError("invalid P3.48 marketplace snapshot schema")
    verified=verify_event_log(list(snap.get("events") or []))
    state=verified["state"]
    checkpoint=dict(snap.get("checkpoint") or {})
    cp=verify_checkpoint(checkpoint,trust_policy)
    body=dict(checkpoint.get("body") or {})
    hashes=[x["event_sha256"] for x in verified["events"]]
    expected={
        "event_count":len(hashes),
        "last_event_sha256":hashes[-1] if hashes else None,
        "merkle_root":merkle_root(hashes),
        "state_sha256":state["state_sha256"],
    }
    for key,value in expected.items():
        if body.get(key)!=value:
            raise RuntimeError(f"P3.48 checkpoint {key} does not match snapshot")
    return {
        "state":state,
        "checkpoint":cp,
        "event_hashes":hashes,
        "snapshot_sha256":_sha({"events":verified["events"],"checkpoint_sha256":cp["checkpoint_sha256"]}),
        "authority":"TRANSPARENCY_SNAPSHOT_VERIFIED_PASS",
    }


def compare_snapshots(left: Mapping[str, Any], right: Mapping[str, Any], trust_policy: Mapping[str, Any]) -> dict:
    a=verify_snapshot(left,trust_policy);b=verify_snapshot(right,trust_policy)
    ah=a["event_hashes"];bh=b["event_hashes"]
    shorter,longer=(ah,bh) if len(ah)<=len(bh) else (bh,ah)
    if len(ah)==len(bh) and ah!=bh:
        verdict="EQUIVOCATION"
    elif longer[:len(shorter)]!=shorter:
        verdict="DIVERGENT_HISTORY"
    elif ah==bh:
        verdict="IDENTICAL"
    else:
        verdict="CONSISTENT_PREFIX"
    return {
        "verdict":verdict,
        "left_event_count":len(ah),"right_event_count":len(bh),
        "left_checkpoint_sha256":a["checkpoint"]["checkpoint_sha256"],
        "right_checkpoint_sha256":b["checkpoint"]["checkpoint_sha256"],
        "authority":"SPLIT_VIEW_REJECTED" if verdict in {"EQUIVOCATION","DIVERGENT_HISTORY"} else "FEDERATED_PREFIX_CONSISTENCY_PASS",
    }


def build_offline_bundle(snapshot: Mapping[str, Any], trust_policy: Mapping[str, Any], package_id: str) -> dict:
    verified=verify_snapshot(snapshot,trust_policy)
    policy=normalize_marketplace_trust_policy(trust_policy)
    row=next((x for x in verified["state"]["packages"] if x["package_id"]==package_id),None)
    if row is None:
        raise RuntimeError("P3.48 package is absent from marketplace snapshot")
    if row["state"]!="PUBLISHED":
        raise RuntimeError("P3.48 offline bundle only admits currently published package")
    body={
        "schema":_BUNDLE_SCHEMA,
        "trust_policy":policy,
        "snapshot":copy.deepcopy(dict(snapshot)),
        "package_id":package_id,
        "published_row":copy.deepcopy(row),
    }
    bundle={**body,"bundle_sha256":_sha(body)}
    rust=_rust("verify-bundle",bundle)
    return {**bundle,"rust_receipt":rust}


def verify_offline_bundle(bundle: Mapping[str, Any], expected_trust_policy: Mapping[str, Any]) -> dict:
    raw=copy.deepcopy(dict(bundle or {}))
    if raw.get("schema")!=_BUNDLE_SCHEMA:
        raise RuntimeError("invalid P3.48 offline bundle schema")
    observed=str(raw.pop("bundle_sha256",""))
    raw.pop("rust_receipt",None)
    if observed!=_sha(raw):
        raise RuntimeError("P3.48 offline bundle seal mismatch")
    expected=normalize_marketplace_trust_policy(expected_trust_policy)
    embedded=normalize_marketplace_trust_policy(dict(raw.get("trust_policy") or {}))
    if embedded["trust_policy_sha256"]!=expected["trust_policy_sha256"]:
        raise RuntimeError("P3.48 offline bundle trust policy does not match pinned policy")
    verified=verify_snapshot(dict(raw.get("snapshot") or {}),expected)
    package_id=str(raw.get("package_id") or "")
    row=next((x for x in verified["state"]["packages"] if x["package_id"]==package_id),None)
    if row is None or row["state"]!="PUBLISHED":
        raise RuntimeError("P3.48 offline bundle package is not currently published")
    rust=_rust("verify-bundle",{**raw,"bundle_sha256":observed})
    return {
        "package_id":package_id,
        "published_row":row,
        "snapshot_sha256":verified["snapshot_sha256"],
        "trust_policy_sha256":expected["trust_policy_sha256"],
        "rust":rust,
        "authority":"OFFLINE_VERIFIABLE_MARKETPLACE_BUNDLE_PASS",
    }
