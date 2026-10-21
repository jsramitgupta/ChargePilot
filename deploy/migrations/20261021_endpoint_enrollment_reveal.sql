BEGIN;

ALTER TABLE endpoint_enrollments
    ADD COLUMN IF NOT EXISTS encrypted_code VARCHAR(512);

COMMIT;
