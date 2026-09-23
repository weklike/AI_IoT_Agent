import asyncio
import logging
from datetime import datetime
from uuid import uuid4

import paho.mqtt.client as mqtt

from backend.app.clocks import DataClock
from backend.app.config import Settings

logger = logging.getLogger(__name__)


class MQTTConnection:
    def __init__(self, settings: Settings, clock: DataClock | None = None):
        self.settings = settings
        self.clock = clock or DataClock()
        self.subscribed = False
        self.queue: asyncio.Queue[tuple[str, bytes, datetime, bool]] = asyncio.Queue(maxsize=4096)
        self.connected = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"backend-{uuid4()}")
        self.client.reconnect_delay_set(min_delay=1, max_delay=4)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message
        self.loop: asyncio.AbstractEventLoop | None = None

    def _set_connected(self, connected: bool) -> None:
        self.connected = connected
        if not connected:
            self.subscribed = False
        logger.info("MQTT connected=%s", connected)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            prefix = self.settings.mqtt_topic_prefix
            client.subscribe(
                [
                    (f"{prefix}/devices/+/telemetry", 1),
                    (f"{prefix}/devices/+/scenario/ack", 1),
                    (f"{prefix}/devices/+/session/report", 1),
                    (f"{prefix}/devices/+/control/ack", 1),
                ]
            )
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._set_connected, not reason_code.is_failure)

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(
                self._set_subscribed, all(not code.is_failure for code in reason_codes)
            )

    def _set_subscribed(self, value: bool):
        self.subscribed = value

    def _on_message(self, client, userdata, message):
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(
                self._enqueue,
                message.topic,
                bytes(message.payload),
                self.clock.now(),
                message.retain,
            )

    def _enqueue(self, topic: str, payload: bytes, received_at: datetime, retained: bool):
        try:
            self.queue.put_nowait((topic, payload, received_at, retained))
        except asyncio.QueueFull:
            logger.error("MQTT_QUEUE_FULL topic=%s", topic)

    def publish(self, topic: str, payload: str):
        if not self.connected:
            return False
        return self.client.publish(topic, payload, qos=1, retain=False).rc == mqtt.MQTT_ERR_SUCCESS

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._set_connected, False)

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=15)
        self.client.loop_start()

    async def close(self) -> None:
        self.client.disconnect()
        await asyncio.to_thread(self.client.loop_stop)
        self.connected = False
