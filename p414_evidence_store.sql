CREATE TABLE IF NOT EXISTS hwpx_p414_agent_key (
    agent_id TEXT NOT NULL,
    key_id TEXT PRIMARY KEY,
    public_key_ed25519_b64 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'REVOKED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    rotation_of TEXT
);

CREATE TABLE IF NOT EXISTS hwpx_p414_agent_key_event (
    event_id TEXT PRIMARY KEY,
    key_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    event_kind TEXT NOT NULL CHECK (event_kind IN ('REGISTERED', 'ROTATED', 'REVOKED')),
    payload_sha256 TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hwpx_p414_receipt_attempt (
    attempt_id UUID PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    key_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    exact_head TEXT,
    product TEXT,
    raw_receipt JSONB NOT NULL,
    signed_payload JSONB,
    canonical_sha256 TEXT NOT NULL,
    validation_result JSONB NOT NULL,
    normalized_evidence JSONB NOT NULL,
    accepted BOOLEAN NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS hwpx_p414_receipt_attempt_job_idx
    ON hwpx_p414_receipt_attempt(agent_id, job_id, received_at);
CREATE INDEX IF NOT EXISTS hwpx_p414_receipt_attempt_nonce_idx
    ON hwpx_p414_receipt_attempt(agent_id, nonce);
CREATE INDEX IF NOT EXISTS hwpx_p414_receipt_attempt_matrix_idx
    ON hwpx_p414_receipt_attempt(product, exact_head, received_at)
    WHERE accepted = TRUE;

CREATE OR REPLACE FUNCTION hwpx_p414_reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'P4.14 evidence attempts and key events are append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS hwpx_p414_receipt_immutable ON hwpx_p414_receipt_attempt;
CREATE TRIGGER hwpx_p414_receipt_immutable
    BEFORE UPDATE OR DELETE ON hwpx_p414_receipt_attempt
    FOR EACH ROW EXECUTE FUNCTION hwpx_p414_reject_mutation();

DROP TRIGGER IF EXISTS hwpx_p414_key_event_immutable ON hwpx_p414_agent_key_event;
CREATE TRIGGER hwpx_p414_key_event_immutable
    BEFORE UPDATE OR DELETE ON hwpx_p414_agent_key_event
    FOR EACH ROW EXECUTE FUNCTION hwpx_p414_reject_mutation();
