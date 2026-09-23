import asyncio
import json
import logging
import signal
import time
from pathlib import Path
from uuid import uuid4

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from backend.app.charging.contracts import ControlCommand, SessionAck
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import DEVICE_IDS, DeviceID, ScenarioCommand, TelemetryV2
from simulator.charging import ChargingDevice
from simulator.reports import ReportDelivery
from simulator.scenarios import SimulatedDevice

logger = logging.getLogger(__name__)


class DeviceClient:
    def __init__(self, device_id: DeviceID, settings: Settings):
        self.device = SimulatedDevice(device_id)
        self.settings = settings
        self.clock = DataClock()
        self.charging = (
            ChargingDevice(
                device_id,
                Path(settings.simulator_state_dir) / f"{device_id}.json",
                self.clock.now(),
                monotonic_ns=time.monotonic_ns(),
            )
            if settings.simulator_mode == "operations"
            else None
        )
        self.delivery = (
            ReportDelivery(
                self.charging,
                expiry_seconds=settings.session_report_expiry_seconds,
                retry_seconds=settings.session_report_retry_seconds,
            )
            if self.charging
            else None
        )
        self.last_report_ns = time.monotonic_ns()
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
            topics = [(self.topic + "/scenario/set", 1)]
            if self.charging:
                topics += [(self.topic + "/control/set", 1), (self.topic + "/session/ack", 1)]
            client.subscribe(topics)

    def _on_message(self, client, userdata, message):
        if self.loop and not message.retain:
            self.loop.call_soon_threadsafe(self._apply, message.topic, bytes(message.payload))

    def _apply(self, topic: str, payload: bytes):
        if len(payload) > 8192:
            return
        if self.charging and topic == self.topic + "/control/set":
            try:
                command = ControlCommand.model_validate_json(payload)
            except ValidationError:
                logger.warning("Rejected control payload device_id=%s", self.device.device_id)
                return
            ack = self.charging.apply(command, self.clock.now(), time.monotonic_ns())
            self.client.publish(
                self.topic + "/control/ack", ack.model_dump_json(), qos=1, retain=False
            )
            return
        if self.delivery and topic == self.topic + "/session/ack":
            try:
                ack = SessionAck.model_validate_json(payload)
            except ValidationError:
                return
            self.delivery.ack(ack, self.clock.now())
            return
        if topic != self.topic + "/scenario/set":
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
        next_sample_ns = 0
        while True:
            now, tick = self.clock.now(), time.monotonic_ns()
            sample_due = tick >= next_sample_ns
            if sample_due:
                next_sample_ns = tick + int(self.settings.telemetry_interval_seconds * 1e9)
                if self.charging:
                    self.charging.checkpoint(now, tick)
            if (
                self.charging
                and tick - self.last_report_ns >= 10_000_000_000
                and self.charging.active
            ):
                self.charging.report(now, tick)
                self.last_report_ns = tick
            if self.client.is_connected():
                if self.delivery:
                    for report in self.delivery.due(now):
                        logger.info(
                            "session_report_attempt device_id=%s report_id=%s",
                            self.device.device_id,
                            report["report_id"],
                        )
                        self.client.publish(
                            self.topic + "/session/report", json.dumps(report), qos=1, retain=False
                        )
                sample = self.device.next_sample(now) if sample_due else None
                if sample:
                    if self.charging:
                        fields = sample.model_dump()
                        fields.update(
                            self.charging.telemetry_fields(),
                            schema_version=2,
                            power_kw=self.charging.actual_power_w / 1000,
                            current_a=self.charging.actual_power_w / 400,
                            operating_state="charging" if self.charging.active else "idle",
                        )
                        sample = TelemetryV2.model_validate(fields)
                    info = self.client.publish(
                        self.topic + "/telemetry", sample.model_dump_json(), qos=1, retain=False
                    )
                    if info.rc == mqtt.MQTT_ERR_SUCCESS:
                        self.pending[info.mid] = str(sample.message_id)
            await asyncio.sleep(0.1 if self.charging else self.settings.telemetry_interval_seconds)

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.charging and self.charging.active:
            now = self.clock.now()
            self.charging.checkpoint(now, time.monotonic_ns())
            self.charging._finish(now, "SIMULATOR_SHUTDOWN")
            self.charging.report(now, time.monotonic_ns())
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
