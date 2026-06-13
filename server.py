#!/usr/bin/env python3
"""DroidMic Server — Receives audio from Android and pipes it to a virtual mic.

Usage:
    python server.py [--port PORT] [--host HOST]

The server listens for WebSocket connections from the DroidMic Android app,
receives raw PCM audio frames, and writes them to a virtual microphone
device so that any desktop application can use the phone's mic as input.
"""

import argparse
import asyncio
import logging
import platform
import signal
import sys

import websockets
from websockets.asyncio.server import ServerConnection

from config import (
    SAMPLE_RATE,
    CHANNELS,
    SAMPLE_WIDTH,
    SERVER_HOST,
    SERVER_PORT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("droidmic")

# Track the single active client
_active_client: ServerConnection | None = None
_client_lock = asyncio.Lock()


def create_audio_sink():
    """Create the platform-appropriate audio sink."""
    system = platform.system().lower()
    if system == "linux":
        from audio_sink_linux import LinuxAudioSink
        return LinuxAudioSink()
    elif system == "windows":
        from audio_sink_windows import WindowsAudioSink
        return WindowsAudioSink()
    else:
        # Fallback: try Linux sink (works for PipeWire on many systems)
        logger.warning(
            "Unsupported platform '%s'. Attempting Linux audio sink.", system
        )
        from audio_sink_linux import LinuxAudioSink
        return LinuxAudioSink()


async def handle_client(websocket: ServerConnection) -> None:
    """Handle a single Android client connection."""
    global _active_client

    client_addr = websocket.remote_address
    logger.info("Client connected: %s", client_addr)

    # Single-client mode: reject if another client is already connected
    async with _client_lock:
        if _active_client is not None:
            logger.warning(
                "Rejecting %s — another client is already connected.", client_addr
            )
            await websocket.close(1013, "Another client is already connected")
            return
        _active_client = websocket

    audio_sink = create_audio_sink()
    frame_count = 0

    try:
        audio_sink.open(SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH)
        logger.info("Audio sink ready. Streaming audio from %s", client_addr)

        async for message in websocket:
            if isinstance(message, bytes):
                audio_sink.write(message)
                frame_count += 1
                if frame_count % 500 == 0:  # Log every ~10 seconds at 20ms chunks
                    logger.info(
                        "Streaming: %d frames received from %s",
                        frame_count, client_addr,
                    )
            # Ignore text messages (could be used for control in future)

    except websockets.exceptions.ConnectionClosed as exc:
        logger.info("Client %s disconnected: %s", client_addr, exc)
    except Exception:
        logger.exception("Error handling client %s", client_addr)
    finally:
        audio_sink.close()
        async with _client_lock:
            _active_client = None
        logger.info(
            "Session ended for %s (%d frames total)", client_addr, frame_count
        )


async def main(host: str, port: int) -> None:
    """Start the DroidMic WebSocket server."""
    logger.info("=" * 50)
    logger.info("  DroidMic Server")
    logger.info("=" * 50)
    logger.info("Listening on ws://%s:%d", host, port)
    logger.info("Audio format: %dHz, %d-bit, %dch (PCM)",
                SAMPLE_RATE, SAMPLE_WIDTH * 8, CHANNELS)
    logger.info("Platform: %s", platform.system())
    logger.info("Waiting for Android client to connect...")
    logger.info("")

    # Graceful shutdown on Ctrl+C
    stop = asyncio.get_event_loop().create_future()

    def _signal_handler() -> None:
        if not stop.done():
            stop.set_result(None)

    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(sig, _signal_handler)

    # TODO(security): Add TLS/WSS support for encrypted transport
    # TODO(security): Add PIN-based client authentication
    async with websockets.serve(
        handle_client,
        host,
        port,
        # Limit frame size to prevent abuse (max ~1 second of audio)
        max_size=SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS * 2,
        # Ping to detect dead connections
        ping_interval=20,
        ping_timeout=10,
    ):
        logger.info("Server started successfully.")
        await stop

    logger.info("Server shutting down...")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DroidMic Server — Use your Android phone as a PC microphone",
    )
    parser.add_argument(
        "--host", default=SERVER_HOST,
        help=f"Host to bind to (default: {SERVER_HOST})",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=SERVER_PORT,
        help=f"Port to listen on (default: {SERVER_PORT})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(main(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(0)
