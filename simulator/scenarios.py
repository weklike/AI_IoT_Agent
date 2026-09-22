import random
from collections import OrderedDict
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from backend.app.contracts import DeviceID, Scenario, ScenarioAck, ScenarioCommand, TelemetryMessage


def generate_sample(
    device_id: DeviceID, boot_id: UUID, seq: int, scenario: Scenario, now: datetime
) -> TelemetryMessage | None:
    if scenario == "offline":
        return None
    rng = random.Random(f"charge-v1:{device_id}:{seq}")
    temperature = rng.uniform(35, 40) if scenario == "normal" else rng.uniform(68, 72)
    return TelemetryMessage(
        schema_version=1,
        device_id=device_id,
        message_id=uuid5(NAMESPACE_URL, f"{device_id}/{boot_id}/{seq}"),
        boot_id=boot_id,
        seq=seq,
        ts=now,
        temperature_c=round(temperature, 2),
        voltage_v=400,
        current_a=50,
        power_kw=20,
        operating_state="charging",
    )


class SimulatedDevice:
    def __init__(self, device_id: DeviceID):
        self.device_id = device_id
        self.boot_id = uuid4()
        self.seq = 0
        self.scenario: Scenario = "normal"
        self.ack_cache: OrderedDict[UUID, ScenarioAck] = OrderedDict()

    def next_sample(self, now: datetime) -> TelemetryMessage | None:
        if self.scenario == "offline":
            return None
        self.seq += 1
        return generate_sample(self.device_id, self.boot_id, self.seq, self.scenario, now)

    def apply_scenario(self, command: ScenarioCommand, now: datetime) -> ScenarioAck:
        if command.command_id in self.ack_cache:
            return self.ack_cache[command.command_id]
        status = "applied" if command.device_id == self.device_id else "rejected"
        if status == "applied":
            self.scenario = command.scenario
        ack = ScenarioAck(**command.model_dump(), status=status, applied_at=now)
        self.ack_cache[command.command_id] = ack
        if len(self.ack_cache) > 100:
            self.ack_cache.popitem(last=False)
        return ack
