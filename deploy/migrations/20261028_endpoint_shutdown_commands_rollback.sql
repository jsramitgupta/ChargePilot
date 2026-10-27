BEGIN;

DROP TABLE IF EXISTS endpoint_shutdown_commands;

UPDATE mappings
SET use_case = 'battery_cycle'
WHERE use_case = 'switch_and_shutdown';

ALTER TABLE mappings
    DROP CONSTRAINT IF EXISTS ck_mappings_use_case;

ALTER TABLE mappings
    ADD CONSTRAINT ck_mappings_use_case
    CHECK (use_case IN ('battery_cycle', 'switch_off_only'));

COMMIT;
