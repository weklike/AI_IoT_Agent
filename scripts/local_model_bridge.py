"""Optional host helper for a loopback-only model endpoint; no credentials or HTTP parsing."""

import argparse
import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from ipaddress import IPv4Address

logger = logging.getLogger(__name__)


def local_address(value: str) -> str:
    address = IPv4Address(value)
    if not address.is_private or address.is_unspecified or address.is_multicast:
        raise ValueError("Listener must be a specific local/private IPv4 address")
    return str(address)


@asynccontextmanager
async def serve_bridge(listen_host: str, listen_port: int, target_port: int):
    active: set[asyncio.Task] = set()

    async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        while data := await asyncio.wait_for(reader.read(65536), timeout=60):
            writer.write(data)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()
            await writer.drain()

    async def connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        task = asyncio.current_task()
        active.add(task)
        upstream_writer = None
        transfers = []
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", target_port), timeout=3
            )
            transfers = [
                asyncio.create_task(pump(reader, upstream_writer)),
                asyncio.create_task(pump(upstream_reader, writer)),
            ]
            await asyncio.gather(*transfers)
        except (OSError, TimeoutError) as exc:
            logger.warning("Model bridge connection ended: %s", type(exc).__name__)
        finally:
            for transfer in transfers:
                transfer.cancel()
            await asyncio.gather(*transfers, return_exceptions=True)
            for stream in (writer, upstream_writer):
                if stream is not None:
                    stream.close()
                    try:
                        await asyncio.wait_for(stream.wait_closed(), timeout=2)
                    except (OSError, TimeoutError):
                        pass
            active.discard(task)

    server = await asyncio.start_server(connected, local_address(listen_host), listen_port)
    try:
        yield server
    finally:
        server.close()
        # Python 3.12 waits for accepted connections as well as the listening socket.
        for task in list(active):
            task.cancel()
        await asyncio.gather(*active, return_exceptions=True)
        await server.wait_closed()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", type=local_address, required=True)
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-port", type=int, required=True)
    args = parser.parse_args()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    async with serve_bridge(args.listen_host, args.listen_port, args.target_port):
        print(
            f"Model bridge ready on {args.listen_host}:{args.listen_port}; upstream is loopback only",
            flush=True,
        )
        await stopped.wait()


if __name__ == "__main__":
    asyncio.run(main())
