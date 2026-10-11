-- Diagnostic correlation only. These values never participate in action policy.
ALTER TABLE operion_actions
    ADD COLUMN IF NOT EXISTS proposal_trace_id text,
    ADD COLUMN IF NOT EXISTS proposal_span_id text,
    ADD COLUMN IF NOT EXISTS approval_trace_id text,
    ADD COLUMN IF NOT EXISTS approval_span_id text;
