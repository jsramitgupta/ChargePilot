BEGIN;

CREATE TABLE IF NOT EXISTS endpoint_automation_20261021_backup (
    endpoint_id VARCHAR(36) PRIMARY KEY,
    automation_enabled BOOLEAN NOT NULL
);

INSERT INTO endpoint_automation_20261021_backup (endpoint_id, automation_enabled)
SELECT id, automation_enabled
FROM endpoints
ON CONFLICT (endpoint_id) DO NOTHING;

UPDATE endpoints
SET automation_enabled = TRUE
WHERE automation_enabled IS FALSE;

COMMIT;
