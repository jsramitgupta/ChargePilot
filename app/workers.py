import asyncio
import json
import logging
import ssl
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.structs import OffsetAndMetadata, TopicPartition
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.messaging import TelemetryOutbox
from app.schemas.telemetry import TelemetryPayload
from app.services.automation_processor import process_telemetry_event

logger = logging.getLogger("chargepilot.workers")
OUTBOX_BATCH_SIZE = 100
OUTBOX_POLL_SECONDS = 0.25
CONSUMER_RETRIES = 5


def _kafka_options() -> dict[str, Any]:
    options: dict[str, Any] = {
        "bootstrap_servers": settings.kafka_bootstrap_servers,
        "security_protocol": settings.kafka_security_protocol,
    }
    if settings.kafka_security_protocol.startswith("SASL_"):
        username = (
            settings.kafka_sasl_username.get_secret_value()
            if settings.kafka_sasl_username
            else ""
        )
        password = (
            settings.kafka_sasl_password.get_secret_value()
            if settings.kafka_sasl_password
            else ""
        )
        if not settings.kafka_sasl_mechanism or not username or not password:
            raise ValueError("Kafka SASL requires a mechanism, username, and password.")
        options.update(
            sasl_mechanism=settings.kafka_sasl_mechanism,
            sasl_plain_username=username,
            sasl_plain_password=password,
        )
    if settings.kafka_security_protocol.endswith("SSL"):
        options["ssl_context"] = ssl.create_default_context(
            cafile=settings.kafka_ssl_ca_file or None
        )
    return options


def _event_from_outbox(row: TelemetryOutbox) -> dict[str, Any]:
    return {
        "event_id": row.id,
        "tenant_id": row.tenant_id,
        "aggregate_key": row.aggregate_key,
        "payload": json.loads(row.payload_json),
    }


def _pending_outbox_statement():
    earlier = aliased(TelemetryOutbox)
    earlier_for_aggregate = (
        select(earlier.id)
        .where(
            earlier.aggregate_key == TelemetryOutbox.aggregate_key,
            or_(
                earlier.created_at < TelemetryOutbox.created_at,
                and_(
                    earlier.created_at == TelemetryOutbox.created_at,
                    earlier.id < TelemetryOutbox.id,
                ),
            ),
        )
        .exists()
    )
    return (
        select(TelemetryOutbox)
        .where(~earlier_for_aggregate)
        .order_by(TelemetryOutbox.created_at, TelemetryOutbox.id)
        .limit(OUTBOX_BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )


async def run_outbox_relay() -> None:
    producer = AIOKafkaProducer(
        **_kafka_options(),
        enable_idempotence=True,
        compression_type="gzip",
    )
    await producer.start()
    try:
        while True:
            published = 0
            with SessionLocal() as db:
                rows = db.execute(_pending_outbox_statement()).scalars().all()
                for row in rows:
                    event = _event_from_outbox(row)
                    await producer.send_and_wait(
                        settings.telemetry_kafka_topic,
                        json.dumps(event, separators=(",", ":")).encode("utf-8"),
                        key=row.aggregate_key.encode("utf-8"),
                    )
                    db.delete(row)
                    published += 1
                if rows:
                    db.commit()

            if published == 0:
                await asyncio.sleep(OUTBOX_POLL_SECONDS)
    finally:
        await producer.stop()


async def run_automation_consumer() -> None:
    consumer = AIOKafkaConsumer(
        settings.telemetry_kafka_topic,
        **_kafka_options(),
        group_id=settings.telemetry_consumer_group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    producer = AIOKafkaProducer(
        **_kafka_options(),
        enable_idempotence=True,
    )
    await producer.start()
    await consumer.start()
    try:
        async for message in consumer:
            event = message.value
            try:
                payload = TelemetryPayload.model_validate(event["payload"])
                tenant_id = event.get("tenant_id")
                endpoint_id = event["payload"]["endpoint_id"]
                event_id = event["event_id"]
            except (KeyError, TypeError, ValueError) as exc:
                await _dead_letter(producer, event, exc)
                await _commit_message(consumer, message)
                continue

            for attempt in range(CONSUMER_RETRIES):
                try:
                    with SessionLocal() as db:
                        await process_telemetry_event(
                            db,
                            event_id=event_id,
                            endpoint_id=endpoint_id,
                            tenant_id=tenant_id,
                            payload=payload,
                        )
                    break
                except Exception as exc:
                    if attempt + 1 == CONSUMER_RETRIES:
                        logger.error(
                            "Telemetry event %s failed after %s attempts (%s)",
                            event_id,
                            CONSUMER_RETRIES,
                            type(exc).__name__,
                        )
                        await _dead_letter(producer, event, exc)
                    else:
                        await asyncio.sleep(min(2**attempt, 10))
            await _commit_message(consumer, message)
    finally:
        await consumer.stop()
        await producer.stop()


async def _dead_letter(
    producer: AIOKafkaProducer,
    event: Any,
    error: Exception,
) -> None:
    await producer.send_and_wait(
        settings.telemetry_dead_letter_topic,
        json.dumps(
            {"event": event, "error_type": type(error).__name__},
            separators=(",", ":"),
            default=str,
        ).encode("utf-8"),
    )
    logger.error("Telemetry event routed to dead-letter topic (%s)", type(error).__name__)


async def _commit_message(consumer: AIOKafkaConsumer, message: Any) -> None:
    await consumer.commit(
        {
            TopicPartition(message.topic, message.partition): OffsetAndMetadata(
                message.offset + 1,
                "",
            ),
        }
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("outbox-relay", "automation-consumer"))
    role = parser.parse_args().role
    asyncio.run(run_outbox_relay() if role == "outbox-relay" else run_automation_consumer())


if __name__ == "__main__":
    main()
