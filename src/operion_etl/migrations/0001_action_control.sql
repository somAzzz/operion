CREATE TABLE IF NOT EXISTS operion_actions (
    action_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    owner_id text NOT NULL,
    action_type text NOT NULL,
    idempotency_key text NOT NULL,
    current_revision integer NOT NULL DEFAULT 1,
    payload_hash text NOT NULL,
    state text NOT NULL,
    expires_at timestamptz NOT NULL,
    compensates_action_id text REFERENCES operion_actions(action_id),
    lease_owner text,
    lease_token text,
    lease_until timestamptz,
    remote_ref text,
    result_json jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (tenant_id, owner_id, action_type, idempotency_key),
    CHECK (state IN (
        'PENDING_APPROVAL', 'APPROVED', 'EXECUTING', 'UNKNOWN',
        'RECONCILING', 'SUCCEEDED', 'REJECTED', 'EXPIRED', 'REVOKED',
        'CONFLICT', 'MANUAL_REVIEW', 'CANCELLED', 'COMPENSATED'
    ))
);

CREATE TABLE IF NOT EXISTS operion_action_revisions (
    action_id text NOT NULL REFERENCES operion_actions(action_id),
    revision integer NOT NULL,
    payload_json jsonb NOT NULL,
    payload_hash text NOT NULL,
    policy_version text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (action_id, revision)
);

CREATE TABLE IF NOT EXISTS operion_action_decisions (
    decision_id text PRIMARY KEY,
    action_id text NOT NULL REFERENCES operion_actions(action_id),
    revision integer NOT NULL,
    actor_id text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('approve', 'reject', 'revoke')),
    request_id text NOT NULL,
    payload_hash text NOT NULL,
    reason text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (actor_id, request_id)
);

CREATE TABLE IF NOT EXISTS operion_action_attempts (
    attempt_id text PRIMARY KEY,
    action_id text NOT NULL REFERENCES operion_actions(action_id),
    revision integer NOT NULL,
    worker_id text NOT NULL,
    lease_token text NOT NULL,
    state text NOT NULL,
    remote_ref text,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS operion_action_events (
    event_id bigserial PRIMARY KEY,
    action_id text NOT NULL REFERENCES operion_actions(action_id),
    event_type text NOT NULL,
    actor_id text NOT NULL,
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    previous_hash text NOT NULL,
    event_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS operion_action_pauses (
    scope text PRIMARY KEY,
    paused boolean NOT NULL,
    reason text NOT NULL,
    updated_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS operion_worker_heartbeats (
    worker_id text PRIMARY KEY,
    state text NOT NULL,
    current_action_id text,
    release_id text,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS operion_e3_stub_effects (
    effect_id text PRIMARY KEY,
    action_id text NOT NULL,
    dedupe_key text NOT NULL UNIQUE,
    payload_hash text NOT NULL,
    effect_kind text NOT NULL DEFAULT 'create',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'operion_action_app') THEN
        CREATE ROLE operion_action_app NOLOGIN;
    END IF;
END;
$$;

GRANT operion_action_app TO CURRENT_USER;
GRANT USAGE ON SCHEMA public TO operion_action_app;
GRANT SELECT, INSERT, UPDATE ON
    operion_actions,
    operion_action_attempts,
    operion_action_pauses,
    operion_worker_heartbeats
TO operion_action_app;
GRANT SELECT, INSERT ON
    operion_action_revisions,
    operion_action_decisions,
    operion_action_events,
    operion_e3_stub_effects
TO operion_action_app;
GRANT USAGE, SELECT ON SEQUENCE operion_action_events_event_id_seq
TO operion_action_app;

CREATE INDEX IF NOT EXISTS idx_operion_actions_claim
    ON operion_actions(state, updated_at);
CREATE INDEX IF NOT EXISTS idx_operion_events_action
    ON operion_action_events(action_id, event_id);
CREATE INDEX IF NOT EXISTS idx_operion_stub_action
    ON operion_e3_stub_effects(action_id);

CREATE OR REPLACE FUNCTION operion_reject_immutable_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'immutable action-control record';
END;
$$;

DROP TRIGGER IF EXISTS operion_revisions_immutable ON operion_action_revisions;
CREATE TRIGGER operion_revisions_immutable
BEFORE UPDATE OR DELETE ON operion_action_revisions
FOR EACH ROW EXECUTE FUNCTION operion_reject_immutable_change();

DROP TRIGGER IF EXISTS operion_decisions_immutable ON operion_action_decisions;
CREATE TRIGGER operion_decisions_immutable
BEFORE UPDATE OR DELETE ON operion_action_decisions
FOR EACH ROW EXECUTE FUNCTION operion_reject_immutable_change();

DROP TRIGGER IF EXISTS operion_events_immutable ON operion_action_events;
CREATE TRIGGER operion_events_immutable
BEFORE UPDATE OR DELETE ON operion_action_events
FOR EACH ROW EXECUTE FUNCTION operion_reject_immutable_change();
