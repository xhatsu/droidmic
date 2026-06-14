"""DroidMic server configuration and audio format constants."""

# ------------------------------------------------------------------
# TLS / Security Settings
# ------------------------------------------------------------------
TLS_CERT_DIR = "~/.droidmic"
TLS_CERT_FILE = "server.crt"
TLS_KEY_FILE = "server.key"

# --- Audio Format ---
SAMPLE_RATE = 44100        # Hz (CD quality, widely supported)
CHANNELS = 1               # Mono (sufficient for microphone)
SAMPLE_WIDTH = 2           # bytes (16-bit signed PCM)
CHUNK_DURATION_MS = 20     # milliseconds per chunk
CHUNK_SIZE = int(SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS * CHUNK_DURATION_MS / 1000)
# 44100 * 2 * 1 * 0.02 = 1764 bytes per chunk

# --- Server ---
SERVER_HOST = "0.0.0.0"    # Listen on all interfaces for LAN access
SERVER_PORT = 8765          # WebSocket port

# --- Virtual Mic ---
VIRTUAL_SINK_NAME = "DroidMic"
VIRTUAL_SOURCE_NAME = "DroidMicInput"
VIRTUAL_SINK_DESCRIPTION = "DroidMic"
VIRTUAL_SOURCE_DESCRIPTION = "DroidMic Microphone"
