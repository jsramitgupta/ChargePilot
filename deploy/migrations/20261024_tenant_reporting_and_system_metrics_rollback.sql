BEGIN;

ALTER TABLE tenants
    DROP CONSTRAINT IF EXISTS ck_tenants_telemetry_interval_minutes;

DROP INDEX IF EXISTS ix_battery_readings_endpoint_timestamp;

ALTER TABLE battery_readings
    DROP COLUMN IF EXISTS system_metrics_json;

ALTER TABLE tenants
    DROP COLUMN IF EXISTS telemetry_interval_minutes;

COMMIT;
