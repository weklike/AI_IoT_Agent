import asyncio
import logging
import signal
from uuid import uuid4

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import DEVICE_IDS, DeviceID, ScenarioCommand
from simulator.scenarios import SimulatedDevice

logger = logging.getLogger(__name__)


class DeviceClient:
    def __init__(self, device_id: DeviceID, settings: Settings):
        self.device = SimulatedDevice(device_id)
        self.settings = settings
        self.clock = DataClock()
        self.client_id = f"sim-{device_id}-{uuid4()}"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
        self.client.reconnect_delay_set(min_delay=1, max_delay=4)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        self.topic = f"{settings.mqtt_topic_prefix}/devices/{device_id}"
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task | None = None
        self.pending: dict[int, str] = {}
        self.confirmed: set[str] = set()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            client.subscribe(self.topic + "/scenario/set", qos=1)

    def _on_message(self, client, userdata, message):
        if self.loop and not message.retain:
            self.loop.call_soon_threadsafe(self._apply, message.topic, bytes(message.payload))

    def _apply(self, topic: str, payload: bytes):
        if len(payload) > 8192 or topic != self.topic + "/scenario/set":
            return
        try:
            command = ScenarioCommand.model_validate_json(payload)
        except ValidationError:
            logger.warning("Rejected scenario payload device_id=%s", self.device.device_id)
            return
        ack = self.device.apply_scenario(command, self.clock.now())
        self.client.publish(
            self.topic + "/scenario/ack", ack.model_dump_json(), qos=1, retain=False
        )

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        if self.loop and not reason_code.is_failure:
            self.loop.call_soon_threadsafe(self._confirmed, mid)

    def _confirmed(self, mid: int):
        message_id = self.pending.pop(mid, None)
        if message_id:
            self.confirmed.add(message_id)
            logger.info(
                "telemetry_puback device_id=%s message_id=%s", self.device.device_id, message_id
            )

    async def start(self):
        self.loop = asyncio.get_running_loop()
        self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=15)
        self.client.loop_start()
        self.task = asyncio.create_task(self._send(), name=self.client_id)

    async def _send(self):
        while True:
            if self.client.is_connected():
                sample = self.device.next_sample(self.clock.now())
                if sample:
                    info = self.client.publish(
                        self.topic + "/telemetry", sample.model_dump_json(), qos=1, retain=False
                    )
                    if info.rc == mqtt.MQTT_ERR_SUCCESS:
                        self.pending[info.mid] = str(sample.message_id)
            await asyncio.sleep(self.settings.telemetry_interval_seconds)

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.client.disconnect()
        await asyncio.to_thread(self.client.loop_stop)


async def run():
    # Model credentials and database configuration are not used by the simulator.
    settings = Settings(llm_mode="fixture")
    devices = [DeviceClient(device_id, settings) for device_id in DEVICE_IDS]
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    try:
        for device in devices:
            await device.start()
        await stop.wait()
    finally:
        for device in devices:
            await device.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
