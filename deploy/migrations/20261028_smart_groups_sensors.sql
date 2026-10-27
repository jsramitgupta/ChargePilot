BEGIN;

CREATE TABLE IF NOT EXISTS smart_groups (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    criteria_json TEXT NOT NULL,
    created_by VARCHAR(36),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_smart_groups_tenant_name
    ON smart_groups (tenant_id, name);

CREATE TABLE IF NOT EXISTS sensor_assignments (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    group_id VARCHAR(36) NOT NULL REFERENCES smart_groups(id) ON DELETE CASCADE,
    sensor_id VARCHAR(64) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_sensor_assignment_group_sensor UNIQUE (group_id, sensor_id)
);

CREATE INDEX IF NOT EXISTS ix_sensor_assignments_group_enabled
    ON sensor_assignments (group_id, enabled);

CREATE TABLE IF NOT EXISTS sensor_executions (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    group_id VARCHAR(36) NOT NULL REFERENCES smart_groups(id) ON DELETE CASCADE,
    assignment_id VARCHAR(36) NOT NULL REFERENCES sensor_assignments(id) ON DELETE CASCADE,
    endpoint_id VARCHAR(36) NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
    sensor_id VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'queued',
    result_json VARCHAR(2048),
    error VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    lease_token_hash VARCHAR(64),
    completed_at TIMESTAMPTZ,
    CONSTRAINT ck_sensor_execution_status
        CHECK (status IN ('queued', 'claimed', 'completed', 'failed', 'cancelled', 'expired'))
);

CREATE INDEX IF NOT EXISTS ix_sensor_executions_endpoint_status
    ON sensor_executions (endpoint_id, status, created_at);
CREATE INDEX IF NOT EXISTS ix_sensor_executions_tenant_created
    ON sensor_executions (tenant_id, created_at);

COMMIT;
