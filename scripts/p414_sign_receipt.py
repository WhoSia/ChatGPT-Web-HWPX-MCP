from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from p414_evidence_service import SCHEMA, canonical_json, canonical_sha256, validate_capture_job


def init_key(private_path: Path, public_path: Path) -> dict:
    if private_path.exists() or public_path.exists():
        raise FileExistsError("refusing to overwrite an existing capture-agent key")
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    private_bytes = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public_bytes = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    # Best-effort owner-only ACL on Windows; the directory lives outside the checkout.
    private_path.write_bytes(private_bytes)
    if os.name == "nt":
        import subprocess
        subprocess.run(["icacls", str(private_path), "/inheritance:r", "/grant:r", f"{os.environ.get('USERDOMAIN', '.') }\\{os.environ.get('USERNAME', '')}:(R,W)"], check=True, capture_output=True)
    public_path.write_text(base64.b64encode(public_bytes).decode("ascii") + "\n", encoding="ascii")
    return {"agent_id": "win-" + uuid.uuid4().hex[:16], "key_id": "win-key-" + uuid.uuid4().hex, "public_key_ed25519_b64": base64.b64encode(public_bytes).decode("ascii"), "private_key_path": str(private_path), "public_key_path": str(public_path)}


def sign_payload(payload_path: Path, private_path: Path, agent_id: str, key_id: str, out: Path) -> dict:
    payload = json.loads(payload_path.read_text(encoding="utf-8-sig"))
    private = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    if not isinstance(private, Ed25519PrivateKey):
        raise TypeError("capture signing key must be Ed25519")
    canonical = canonical_json(payload)
    signature = private.sign(canonical)
    receipt = {"schema": SCHEMA, "agent_id": agent_id, "key_id": key_id, "signed_payload": payload, "signature_ed25519_b64": base64.b64encode(signature).decode("ascii"), "canonical_sha256": canonical_sha256(payload)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    key_parser = sub.add_parser("init-key")
    key_parser.add_argument("--private", type=Path, required=True)
    key_parser.add_argument("--public", type=Path, required=True)
    validate_parser = sub.add_parser("validate-job")
    validate_parser.add_argument("--job", type=Path, required=True)
    sign_parser = sub.add_parser("sign")
    sign_parser.add_argument("--payload", type=Path, required=True)
    sign_parser.add_argument("--private", type=Path, required=True)
    sign_parser.add_argument("--agent-id", required=True)
    sign_parser.add_argument("--key-id", required=True)
    sign_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "init-key":
        print(json.dumps(init_key(args.private, args.public), ensure_ascii=False))
    elif args.command == "validate-job":
        result = validate_capture_job(json.loads(args.job.read_text(encoding="utf-8-sig")))
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0 if result["status"] == "PASS" else 2)
    else:
        receipt = sign_payload(args.payload, args.private, args.agent_id, args.key_id, args.out)
        print(json.dumps({"receipt_path": str(args.out), "evidence_id": canonical_sha256(receipt), "canonical_sha256": receipt["canonical_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
