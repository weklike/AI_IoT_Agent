import asyncio

import pytest

from scripts.local_model_bridge import local_address, serve_bridge


@pytest.mark.parametrize("address", ["0.0.0.0", "8.8.8.8", "224.0.0.1"])
def test_bridge_refuses_public_or_wildcard_listener(address):
    with pytest.raises(ValueError):
        local_address(address)


async def test_bridge_preserves_bytes_and_half_close():
    async def upstream(reader, writer):
        request = await reader.read()
        writer.write(b"response:" + request)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(upstream, "127.0.0.1", 0)
    try:
        async with serve_bridge("127.0.0.1", 0, server.sockets[0].getsockname()[1]) as bridge:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", bridge.sockets[0].getsockname()[1]
            )
            writer.write(b"opaque-test-payload")
            await writer.drain()
            writer.write_eof()
            assert await asyncio.wait_for(reader.read(), 2) == b"response:opaque-test-payload"
            writer.close()
            await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()


async def test_bridge_shutdown_closes_idle_client():
    connected, closed = asyncio.Event(), asyncio.Event()

    async def upstream(reader, writer):
        connected.set()
        await reader.read()
        writer.close()
        await writer.wait_closed()
        closed.set()

    server = await asyncio.start_server(upstream, "127.0.0.1", 0)
    try:
        async with (
            asyncio.timeout(2),
            serve_bridge("127.0.0.1", 0, server.sockets[0].getsockname()[1]) as bridge,
        ):
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", bridge.sockets[0].getsockname()[1]
            )
            await asyncio.wait_for(connected.wait(), 2)
        assert await asyncio.wait_for(reader.read(), 2) == b""
        await asyncio.wait_for(closed.wait(), 2)
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()
