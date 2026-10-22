BEGIN;

ALTER TABLE devices
    ADD COLUMN IF NOT EXISTS power_dp_id VARCHAR(50),
    ADD COLUMN IF NOT EXISTS power_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS energy_dp_id VARCHAR(50),
    ADD COLUMN IF NOT EXISTS energy_multiplier DOUBLE PRECISION NOT NULL DEFAULT 0.001,
    ADD COLUMN IF NOT EXISTS energy_counter_type VARCHAR(16) NOT NULL DEFAULT 'cumulative',
    ADD COLUMN IF NOT EXISTS meter_power_watts DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS meter_power_sample_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS meter_energy_month_kwh DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS meter_energy_sample_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS meter_energy_total_kwh DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS meter_month_key VARCHAR(7),
    ADD COLUMN IF NOT EXISTS meter_last_sample_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS meter_poll_requested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS meter_tracking_since TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_devices_meter_poll
    ON devices (connector_id, meter_last_sample_at)
    WHERE enabled IS TRUE
      AND (power_dp_id IS NOT NULL OR energy_dp_id IS NOT NULL);

COMMIT;
