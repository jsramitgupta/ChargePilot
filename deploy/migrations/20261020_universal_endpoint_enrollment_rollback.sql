BEGIN;

UPDATE endpoint_enrollments
SET platform = 'windows',
    used_at = COALESCE(used_at, last_used_at, expires_at)
WHERE platform IS NULL;

ALTER TABLE endpoint_enrollments
    ALTER COLUMN platform SET NOT NULL,
    DROP COLUMN IF EXISTS enrollment_count,
    DROP COLUMN IF EXISTS last_used_at;

COMMIT;
