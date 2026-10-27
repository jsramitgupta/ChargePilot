BEGIN;

ALTER TABLE mappings
    ADD COLUMN IF NOT EXISTS use_case VARCHAR(32) NOT NULL DEFAULT 'battery_cycle';

UPDATE mappings
SET use_case = 'battery_cycle'
WHERE use_case IS NULL;

ALTER TABLE mappings
    ALTER COLUMN use_case SET DEFAULT 'battery_cycle',
    ALTER COLUMN use_case SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_mappings_use_case'
          AND conrelid = 'mappings'::regclass
    ) THEN
        ALTER TABLE mappings
            ADD CONSTRAINT ck_mappings_use_case
            CHECK (use_case IN ('battery_cycle', 'switch_off_only'));
    END IF;
END $$;

COMMIT;
