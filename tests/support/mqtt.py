import asyncio
import json
from uuid import uuid4

import paho.mqtt.client as mqtt


class MQTTProbe:
    def __init__(self, port: int, prefix: str):
        self.port, self.prefix = port, prefix
        self.messages: list[tuple[str, dict]] = []
        self.ready = asyncio.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"probe-{uuid4()}")
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, code, properties):
        client.subscribe(f"{self.prefix}/#", qos=1)

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        self.loop.call_soon_threadsafe(self.ready.set)

    def on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload)
        except (ValueError, UnicodeError):
            return
        self.loop.call_soon_threadsafe(self.messages.append, (message.topic, payload))

    async def start(self):
        self.loop = asyncio.get_running_loop()
        self.client.connect_async("127.0.0.1", self.port)
        self.client.loop_start()
        await asyncio.wait_for(self.ready.wait(), 10)

    async def wait_for(self, predicate, timeout=6):
        async with asyncio.timeout(timeout):
            while True:
                for topic, payload in self.messages:
                    if predicate(topic, payload):
                        return payload
                await asyncio.sleep(0.02)

    async def close(self):
        self.client.disconnect()
        await asyncio.to_thread(self.client.loop_stop)
