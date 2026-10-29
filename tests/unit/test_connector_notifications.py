import asyncio

from app.services.connector_notifications import ConnectorWebSocketManager
from app.services.connector_service import _notify_connector_command_available
from connector.chargepilot_connector import _websocket_url


class _FakeWebSocket:
    def __init__(self) -> None:
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


def test_websocket_url_preserves_configured_server_path():
    assert _websocket_url("https://chargepilot.example/base/") == (
        "wss://chargepilot.example/base/api/v1/connectors/ws"
    )
    assert _websocket_url("http://127.0.0.1:8000") == (
        "ws://127.0.0.1:8000/api/v1/connectors/ws"
    )


def test_connector_notifications_reach_only_matching_connections():
    async def run_test():
        manager = ConnectorWebSocketManager()
        first = _FakeWebSocket()
        second = _FakeWebSocket()
        await manager.connect("connector-a", first)
        await manager.connect("connector-b", second)

        await manager.publish("connector-a")

        assert first.messages == [{"type": "commands_available"}]
        assert second.messages == []

        await manager.disconnect("connector-a", first)
        await manager.publish("connector-a")
        assert first.messages == [{"type": "commands_available"}]

    asyncio.run(run_test())


def test_command_notification_uses_transactional_postgres_notify():
    class FakeDatabase:
        class bind:
            class dialect:
                name = "postgresql"

        def __init__(self):
            self.executed = []

        def get_bind(self):
            return self.bind

        def execute(self, statement, params):
            self.executed.append((str(statement), params))

    db = FakeDatabase()
    _notify_connector_command_available(db, "connector-id")

    assert len(db.executed) == 1
    statement, params = db.executed[0]
    assert "pg_notify('chargepilot_connector_commands'" in statement
    assert params == {"connector_id": "connector-id"}


def test_command_notification_is_skipped_for_sqlite():
    class FakeDatabase:
        class bind:
            class dialect:
                name = "sqlite"

        def get_bind(self):
            return self.bind

        def execute(self, *_args):
            raise AssertionError("SQLite must not execute PostgreSQL notification SQL.")

    _notify_connector_command_available(FakeDatabase(), "connector-id")
