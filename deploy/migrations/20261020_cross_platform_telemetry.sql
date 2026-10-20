BEGIN;

ALTER TABLE endpoints
    ADD COLUMN IF NOT EXISTS installation_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS platform VARCHAR(16) NOT NULL DEFAULT 'windows',
    ADD COLUMN IF NOT EXISTS device_class VARCHAR(16),
    ADD COLUMN IF NOT EXISTS automation_enabled BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE endpoints
    ALTER COLUMN ac_connected DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ix_endpoints_token_hash
    ON endpoints (token_hash)
    WHERE token_hash IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ix_endpoints_installation_id
    ON endpoints (installation_id)
    WHERE installation_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS endpoint_enrollments (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform VARCHAR(16) NOT NULL,
    code_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
