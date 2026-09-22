from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from backend.app.contracts import TelemetryMessage

T0 = datetime(2026, 9, 22, 8, 10, tzinfo=UTC)


async def load_dataset(store, case_id: str, repeat: int, profile="baseline"):
    series = {
        "CHG-001": [(-8, 35), (-6, 36), (-4, 37), (-2, 38), (0, 39)],
        "CHG-002": [(-8, 58), (-6, 61), (-4, 65), (-2, 70), (0, 72)],
        "CHG-003": [(-20, 37)],
    }
    if profile == "empty":
        series["CHG-001"] = []
    if profile == "recovered":
        series["CHG-002"] = [(-300, 72), (0, 38)]
    for device, points in series.items():
        boot = uuid5(NAMESPACE_URL, f"{case_id}/{repeat}/{device}/boot")
        for seq, (offset, temperature) in enumerate(points, 1):
            ts = T0 + timedelta(seconds=offset)
            sample = TelemetryMessage(
                schema_version=1,
                device_id=device,
                message_id=uuid5(NAMESPACE_URL, f"{case_id}/{repeat}/{device}/{seq}"),
                boot_id=boot,
                seq=seq,
                ts=ts,
                temperature_c=temperature,
                voltage_v=400,
                current_a=50,
                power_kw=20,
                operating_state="charging",
            )
            await store.ingest(sample, ts)
