BEGIN;

ALTER TABLE endpoint_enrollments
    DROP COLUMN IF EXISTS encrypted_code;

COMMIT;
