CREATE TABLE api_tokens (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL,
    user_id    uuid NOT NULL,
    token_hash text NOT NULL UNIQUE,
    label      text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    FOREIGN KEY (tenant_id, user_id) REFERENCES users (tenant_id, id)
);