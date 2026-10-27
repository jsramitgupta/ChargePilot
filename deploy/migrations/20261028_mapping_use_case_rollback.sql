BEGIN;

ALTER TABLE mappings
    DROP CONSTRAINT IF EXISTS ck_mappings_use_case;

ALTER TABLE mappings
    DROP COLUMN IF EXISTS use_case;

COMMIT;
