BEGIN;

DROP INDEX IF EXISTS ix_devices_meter_poll;

ALTER TABLE devices
    DROP COLUMN IF EXISTS meter_tracking_since,
    DROP COLUMN IF EXISTS meter_poll_requested_at,
    DROP COLUMN IF EXISTS meter_last_sample_at,
    DROP COLUMN IF EXISTS meter_month_key,
    DROP COLUMN IF EXISTS meter_energy_total_kwh,
    DROP COLUMN IF EXISTS meter_energy_month_kwh,
    DROP COLUMN IF EXISTS meter_energy_sample_at,
    DROP COLUMN IF EXISTS meter_power_watts,
    DROP COLUMN IF EXISTS meter_power_sample_at,
    DROP COLUMN IF EXISTS energy_counter_type,
    DROP COLUMN IF EXISTS energy_multiplier,
    DROP COLUMN IF EXISTS energy_dp_id,
    DROP COLUMN IF EXISTS power_multiplier,
    DROP COLUMN IF EXISTS power_dp_id;

COMMIT;
