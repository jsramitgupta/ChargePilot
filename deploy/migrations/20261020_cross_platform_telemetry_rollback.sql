BEGIN;

UPDATE endpoints SET ac_connected = FALSE WHERE ac_connected IS NULL;

DROP TABLE IF EXISTS endpoint_enrollments;
DROP INDEX IF EXISTS ix_endpoints_token_hash;
DROP INDEX IF EXISTS ix_endpoints_installation_id;

ALTER TABLE endpoints
    ALTER COLUMN ac_connected SET NOT NULL,
    DROP COLUMN IF EXISTS installation_id,
    DROP COLUMN IF EXISTS platform,
    DROP COLUMN IF EXISTS device_class,
    DROP COLUMN IF EXISTS automation_enabled;

COMMIT;
