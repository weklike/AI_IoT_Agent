import asyncio
import logging
from uuid import uuid4

import paho.mqtt.client as mqtt

from backend.app.config import Settings

logger = logging.getLogger(__name__)


class MQTTConnection:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.connected = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"backend-{uuid4()}")
        self.client.reconnect_delay_set(min_delay=1, max_delay=4)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.loop: asyncio.AbstractEventLoop | None = None

    def _set_connected(self, connected: bool) -> None:
        self.connected = connected
        logger.info("MQTT connected=%s", connected)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._set_connected, not reason_code.is_failure)

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
