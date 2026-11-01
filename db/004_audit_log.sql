CREATE TABLE audit_log (
    id        bigserial PRIMARY KEY,
    at        timestamptz NOT NULL DEFAULT now(),
    event     text NOT NULL,                      -- 'auth' or 'tool_call'
    outcome   text NOT NULL CHECK (outcome IN ('allow', 'deny')),
    reason    text NOT NULL,                      -- fixed vocabulary from our code, never user input
    tenant_id uuid,
    user_id   uuid,
    token_ref text,                               -- first 12 hex chars of the token HASH
    tool      text,
    target    text                                -- a validated UUID or 'invalid-id', never raw input
);
CREATE INDEX audit_log_at_idx ON audit_log (at DESC);
CREATE INDEX audit_log_user_idx ON audit_log (user_id, at DESC);
CREATE INDEX audit_log_token_idx ON audit_log (token_ref, at DESC);