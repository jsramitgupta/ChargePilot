import argparse
import os
import sys
from time import perf_counter
from urllib.parse import urlsplit

import psycopg


DEFAULT_ROWS = 10_000_001


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and query a temporary synthetic 10M+ endpoint dataset in PostgreSQL."
    )
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--tenants", type=int, default=1_000)
    args = parser.parse_args()
    database_url = os.environ.get("CHARGEPILOT_SCALE_DATABASE_URL", "")
    database_name = urlsplit(database_url).path.rsplit("/", 1)[-1]
    if not database_url or not database_name.endswith("_scale_test"):
        print(
            "Set CHARGEPILOT_SCALE_DATABASE_URL to a disposable PostgreSQL database "
            "whose name ends with _scale_test.",
            file=sys.stderr,
        )
        return 2
    if args.rows <= 10_000_000 or args.tenants < 1:
        parser.error("--rows must exceed 10,000,000 and --tenants must be positive")

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TEMP TABLE scale_endpoints (
                    id BIGINT NOT NULL,
                    tenant_id INTEGER NOT NULL,
                    hostname VARCHAR(160) NOT NULL,
                    battery_percentage SMALLINT NOT NULL,
                    last_seen_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (tenant_id, id)
                ) ON COMMIT PRESERVE ROWS
                """
            )
            cursor.execute(
                """
                CREATE INDEX ix_scale_endpoints_tenant_hostname
                ON scale_endpoints (tenant_id, hostname)
                """
            )
            started = perf_counter()
            cursor.execute(
                """
                INSERT INTO scale_endpoints
                    (id, tenant_id, hostname, battery_percentage, last_seen_at)
                SELECT n,
                       ((n - 1) % %s)::INTEGER,
                       'endpoint-' || n::TEXT,
                       (n % 101)::SMALLINT,
                       now()
                FROM generate_series(1, %s) AS n
                """,
                (args.tenants, args.rows),
            )
            connection.commit()
            seed_seconds = perf_counter() - started
            cursor.execute("SELECT count(*) FROM scale_endpoints")
            actual_rows = cursor.fetchone()[0]
            if actual_rows != args.rows:
                raise RuntimeError(f"Expected {args.rows} rows, found {actual_rows}.")

            tenant_id = ((args.rows // 2) - 1) % args.tenants
            endpoint_id = args.rows // 2
            query_started = perf_counter()
            cursor.execute(
                """
                SELECT battery_percentage, last_seen_at
                FROM scale_endpoints
                WHERE tenant_id = %s AND hostname = %s
                """,
                (tenant_id, f"endpoint-{endpoint_id}"),
            )
            result = cursor.fetchone()
            lookup_ms = (perf_counter() - query_started) * 1_000
            if result is None:
                raise RuntimeError("Indexed tenant/hostname lookup returned no row.")

    print(f"Synthetic endpoint rows verified: {actual_rows:,}")
    print(f"Tenant count: {args.tenants:,}")
    print(f"Seed time: {seed_seconds:.2f}s")
    print(f"Indexed tenant/hostname lookup: {lookup_ms:.2f}ms")
    print("The dataset was temporary and was dropped when the connection closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
