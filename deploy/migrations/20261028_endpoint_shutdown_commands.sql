BEGIN;

ALTER TABLE mappings
    DROP CONSTRAINT IF EXISTS ck_mappings_use_case;

ALTER TABLE mappings
    ADD CONSTRAINT ck_mappings_use_case
    CHECK (use_case IN ('battery_cycle', 'switch_off_only', 'switch_and_shutdown'));

CREATE TABLE IF NOT EXISTS endpoint_shutdown_commands (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    endpoint_id VARCHAR(36) NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
    mapping_id VARCHAR(36) NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
    automation_event_id VARCHAR(36) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    error VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CONSTRAINT ck_endpoint_shutdown_status
        CHECK (status IN ('pending', 'claimed', 'scheduled', 'cancelled', 'failed', 'expired')),
    CONSTRAINT uq_endpoint_shutdown_event
        UNIQUE (endpoint_id, mapping_id, automation_event_id)
);

CREATE INDEX IF NOT EXISTS ix_endpoint_shutdown_pending
    ON endpoint_shutdown_commands (endpoint_id, status, expires_at);
CREATE INDEX IF NOT EXISTS ix_endpoint_shutdown_commands_tenant_id
    ON endpoint_shutdown_commands (tenant_id);
CREATE INDEX IF NOT EXISTS ix_endpoint_shutdown_commands_status
    ON endpoint_shutdown_commands (status);

COMMIT;
