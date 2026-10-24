BEGIN;

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS telemetry_interval_minutes INTEGER NOT NULL DEFAULT 5;

ALTER TABLE battery_readings
    ADD COLUMN IF NOT EXISTS system_metrics_json TEXT;

CREATE INDEX IF NOT EXISTS ix_battery_readings_endpoint_timestamp
    ON battery_readings (endpoint_id, timestamp);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_tenants_telemetry_interval_minutes'
          AND conrelid = 'tenants'::regclass
    ) THEN
        ALTER TABLE tenants
            ADD CONSTRAINT ck_tenants_telemetry_interval_minutes
            CHECK (telemetry_interval_minutes BETWEEN 5 AND 1440);
    END IF;
END $$;

COMMIT;
