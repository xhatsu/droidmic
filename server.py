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
import functools
import json
import logging
import platform
import signal
import sys
import time

import websockets
from websockets.asyncio.server import ServerConnection

from config import (
    SAMPLE_RATE,
    CHANNELS,
    SAMPLE_WIDTH,
    SERVER_HOST,
    SERVER_PORT,
)
from discovery import DroidMicServiceAdvertiser
from pairing import PairingManager
from tls_manager import TLSManager

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


async def handle_client(websocket: ServerConnection, quiet: bool = False, pairing_manager: PairingManager = None, no_auth: bool = False, cert_fingerprint: str = "") -> None:
    """Handle incoming WebSocket connection from an Android client."""
    client_addr = websocket.remote_address
    logger.info("New client connected from %s", client_addr)

    # ------------------------------------------------------------------
    # Authentication & Pairing Phase
    # ------------------------------------------------------------------
    if not no_auth:
        paired = False
        device_name = "Unknown Device"
        device_id = "unknown"
        
        try:
            # Wait for first message, which must be JSON pairing request or auth info
            first_msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            if isinstance(first_msg, str):
                data = json.loads(first_msg)
                msg_type = data.get("type")
                device_name = data.get("device_name", "Unknown Device")
                device_id = data.get("device_id", "unknown")
                
                if msg_type == "auth_check":
                    # Client claims to be paired
                    if pairing_manager.is_device_paired(device_id):
                        logger.info("Client '%s' (%s) is already paired.", device_name, device_id)
                        await websocket.send(json.dumps({"type": "auth_success"}))
                        paired = True
                    else:
                        logger.info("Client '%s' (%s) not paired. Requesting pairing...", device_name, device_id)
                        await websocket.send(json.dumps({"type": "auth_failed"}))
                        # Wait for them to request pairing
                
                if msg_type == "pair_request" or not paired:
                    if msg_type != "pair_request":
                        # We might get here if auth failed and they retry, but usually they'll disconnect and reconnect
                        # Let's wait for the pair_request
                        msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        if isinstance(msg, str):
                            data = json.loads(msg)
                            msg_type = data.get("type")
                            if msg_type == "pair_request":
                                device_name = data.get("device_name", "Unknown Device")
                                device_id = data.get("device_id", "unknown")
                    
                    if msg_type == "pair_request":
                        # Start pairing process
                        pairing_manager.generate_pin(device_name)
                        await websocket.send(json.dumps({"type": "pair_challenge"}))
                        
                        # Wait for pin response
                        resp_msg = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                        if isinstance(resp_msg, str):
                            resp_data = json.loads(resp_msg)
                            if resp_data.get("type") == "pair_response":
                                provided_pin = resp_data.get("pin", "")
                                if pairing_manager.verify_pin(device_id, device_name, provided_pin):
                                    await websocket.send(json.dumps({
                                        "type": "pair_success",
                                        "cert_fingerprint": cert_fingerprint
                                    }))
                                    paired = True
                                else:
                                    await websocket.send(json.dumps({"type": "pair_failed", "reason": "Invalid PIN"}))
                                    await websocket.close(1008, "Invalid PIN")
                                    return
            else:
                logger.warning("Expected JSON authentication message, received binary.")
                await websocket.close(1008, "Auth required")
                return
                
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for authentication from %s", client_addr)
            pairing_manager.cancel_pairing()
            await websocket.close(1008, "Auth timeout")
            return
        except Exception as e:
            logger.error("Error during authentication: %s", e)
            pairing_manager.cancel_pairing()
            await websocket.close(1011, "Auth error")
            return
            
        if not paired:
            logger.warning("Client %s failed authentication", client_addr)
            await websocket.close(1008, "Auth failed")
            return

    # ------------------------------------------------------------------
    # Audio Streaming Phase
    # ------------------------------------------------------------------

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
    start_time = time.time()
    last_log_time = start_time
    
    # Jitter buffer to prevent infinite delay accumulation.
    # 5 frames * 20ms = 100ms max queue latency.
    # If the network lags and suddenly sends a burst of frames,
    # we drop the old ones to catch up to real-time.
    jitter_buffer: asyncio.Queue[bytes] = asyncio.Queue(maxsize=5)

    try:
        audio_sink.open(SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH)
        logger.info("Audio sink ready. Streaming audio from %s", client_addr)

        # Background task to write to PyAudio without blocking the WebSocket loop
        async def play_audio():
            loop = asyncio.get_running_loop()
            while True:
                chunk = await jitter_buffer.get()
                # Run the blocking write in a thread pool to avoid blocking asyncio
                await loop.run_in_executor(None, audio_sink.write, chunk)
                jitter_buffer.task_done()

        playback_task = asyncio.create_task(play_audio())

        async for message in websocket:
            if isinstance(message, bytes):
                # If the buffer is full, drop the oldest frame to catch up!
                if jitter_buffer.full():
                    try:
                        jitter_buffer.get_nowait()
                        logger.warning("Network burst detected! Dropping old audio frame to reduce latency.")
                    except asyncio.QueueEmpty:
                        pass
                
                await jitter_buffer.put(message)
                
                frame_count += 1
                if frame_count % 500 == 0:  # 500 frames of 20ms = 10.0 seconds of audio
                    now = time.time()
                    elapsed = now - last_log_time
                    last_log_time = now
                    delay_rate = elapsed / 10.0
                    if not quiet:
                        logger.info(
                            "Streaming: 500 frames received. Elapsed: %.2fs (Delay Rate: %.2fx)",
                            elapsed, delay_rate
                        )

    except websockets.exceptions.ConnectionClosed as exc:
        logger.info("Client %s disconnected: %s", client_addr, exc)
    except Exception:
        logger.exception("Error handling client %s", client_addr)
    finally:
        if 'playback_task' in locals():
            playback_task.cancel()
        audio_sink.close()
        async with _client_lock:
            _active_client = None
        logger.info(
            "Session ended for %s (%d frames total)", client_addr, frame_count
        )


async def main(host: str, port: int, quiet: bool, no_mdns: bool, no_tls: bool, no_auth: bool) -> None:
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

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_event_loop().add_signal_handler(sig, _signal_handler)
    except NotImplementedError:
        # Signal handlers are not supported on Windows (ProactorEventLoop).
        # KeyboardInterrupt will naturally break the asyncio loop.
        pass

    # Initialize TLS if enabled
    ssl_context = None
    cert_fingerprint = ""
    if not no_tls:
        tls_manager = TLSManager()
        if tls_manager.initialize():
            ssl_context = tls_manager.get_ssl_context()
            cert_fingerprint = tls_manager.get_fingerprint()
            logger.info("TLS is ENABLED (wss://). Fingerprint: %s", cert_fingerprint)
        else:
            logger.warning("TLS initialization failed. Falling back to unencrypted (ws://).")
    else:
        logger.warning("TLS is DISABLED (ws://) via --no-tls flag.")
        
    pairing_manager = PairingManager()
    if no_auth:
        logger.warning("PIN pairing authentication is DISABLED via --no-auth flag.")

    handler = functools.partial(
        handle_client, 
        quiet=quiet, 
        pairing_manager=pairing_manager, 
        no_auth=no_auth, 
        cert_fingerprint=cert_fingerprint
    )
    
    advertiser = None
    if not no_mdns:
        advertiser = DroidMicServiceAdvertiser(port=port, use_tls=ssl_context is not None, cert_fingerprint=cert_fingerprint)
        advertiser.start()

    try:
        async with websockets.serve(
            handler,
            host,
            port,
            ssl=ssl_context,
            # Limit frame size to prevent abuse (max ~1 second of audio)
            max_size=SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS * 2,
            # Ping to detect dead connections
            ping_interval=20,
            ping_timeout=10,
        ):
            logger.info("Server started successfully.")
            await stop
    finally:
        if advertiser:
            advertiser.stop()

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
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress periodic streaming status logs",
    )
    parser.add_argument(
        "--no-mdns", action="store_true",
        help="Disable mDNS service advertisement",
    )
    parser.add_argument(
        "--no-tls", action="store_true",
        help="Disable TLS encryption (use ws:// instead of wss://)",
    )
    parser.add_argument(
        "--no-auth", action="store_true",
        help="Disable PIN pairing authentication (accept all connections)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(main(args.host, args.port, args.quiet, args.no_mdns, args.no_tls, args.no_auth))
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(0)
