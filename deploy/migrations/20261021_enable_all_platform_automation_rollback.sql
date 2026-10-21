BEGIN;

UPDATE endpoints
SET automation_enabled = FALSE
WHERE installation_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM endpoint_automation_20261021_backup AS previous
      WHERE previous.endpoint_id = endpoints.id
  );

UPDATE endpoints AS endpoint
SET automation_enabled = previous.automation_enabled
FROM endpoint_automation_20261021_backup AS previous
WHERE endpoint.id = previous.endpoint_id;

DROP TABLE endpoint_automation_20261021_backup;

COMMIT;
