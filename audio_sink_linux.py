"""Linux audio sink using PulseAudio/PipeWire null sink.

Creates a virtual microphone device via pactl and writes PCM audio
to it using PyAudio, so any application can select it as a mic input.
"""

import logging
import subprocess
import shutil

import pyaudio

from audio_sink import AudioSink
from config import (
    VIRTUAL_SINK_NAME,
    VIRTUAL_SOURCE_NAME,
    VIRTUAL_SINK_DESCRIPTION,
    VIRTUAL_SOURCE_DESCRIPTION,
)

logger = logging.getLogger(__name__)


class LinuxAudioSink(AudioSink):
    """Writes PCM audio to a PulseAudio/PipeWire virtual microphone."""

    def __init__(self) -> None:
        self._pa: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None
        self._sink_module_id: int | None = None
        self._source_module_id: int | None = None
        self._opened = False

    # ------------------------------------------------------------------
    # Virtual device management
    # ------------------------------------------------------------------

    def _ensure_pactl(self) -> None:
        """Verify that pactl is available on the system."""
        if not shutil.which("pactl"):
            raise RuntimeError(
                "pactl not found. Install PulseAudio or PipeWire-Pulse:\n"
                "  sudo apt install pulseaudio-utils   # Debian/Ubuntu\n"
                "  sudo pacman -S libpulse              # Arch"
            )

    def _create_virtual_sink(self, sample_rate: int, channels: int) -> None:
        """Create a PulseAudio null sink + remap source."""
        self._ensure_pactl()

        # Remove any existing DroidMic modules to avoid duplicates
        self._destroy_virtual_sink()

        # Create null sink (virtual speaker we write audio into)
        result = subprocess.run(
            [
                "pactl", "load-module", "module-null-sink",
                f"sink_name={VIRTUAL_SINK_NAME}",
                f"sink_properties=device.description={VIRTUAL_SINK_DESCRIPTION}",
                f"rate={sample_rate}",
                f"channels={channels}",
                "format=s16le",
            ],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create null sink: {result.stderr.strip()}")
        self._sink_module_id = int(result.stdout.strip())
        logger.info("Created null sink (module %d)", self._sink_module_id)

        # Remap the sink's monitor as a source (appears as a microphone)
        result = subprocess.run(
            [
                "pactl", "load-module", "module-remap-source",
                f"master={VIRTUAL_SINK_NAME}.monitor",
                f"source_name={VIRTUAL_SOURCE_NAME}",
                f"source_properties=device.description={VIRTUAL_SOURCE_DESCRIPTION}",
            ],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create remap source: {result.stderr.strip()}")
        self._source_module_id = int(result.stdout.strip())
        logger.info("Created remap source (module %d)", self._source_module_id)

    def _destroy_virtual_sink(self) -> None:
        """Unload DroidMic PulseAudio modules if they exist."""
        if self._source_module_id is not None:
            subprocess.run(
                ["pactl", "unload-module", str(self._source_module_id)],
                capture_output=True, check=False,
            )
            self._source_module_id = None

        if self._sink_module_id is not None:
            subprocess.run(
                ["pactl", "unload-module", str(self._sink_module_id)],
                capture_output=True, check=False,
            )
            self._sink_module_id = None

    def _find_sink_index(self) -> int | None:
        """Find the PyAudio device index for the DroidMic sink."""
        if self._pa is None:
            return None

        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            name = info.get("name", "")
            if VIRTUAL_SINK_NAME in name and info.get("maxOutputChannels", 0) > 0:
                return i
        return None

    # ------------------------------------------------------------------
    # AudioSink interface
    # ------------------------------------------------------------------

    def open(self, sample_rate: int, channels: int, sample_width: int) -> None:
        """Create virtual mic and open PyAudio stream to it."""
        if self._opened:
            return

        # Create the virtual PulseAudio devices
        self._create_virtual_sink(sample_rate, channels)

        # Open PyAudio output stream targeting the null sink
        self._pa = pyaudio.PyAudio()
        device_index = self._find_sink_index()

        fmt = self._pa.get_format_from_width(sample_width)
        self._stream = self._pa.open(
            format=fmt,
            channels=channels,
            rate=sample_rate,
            output=True,
            output_device_index=device_index,
            frames_per_buffer=1024,
        )
        self._opened = True
        logger.info(
            "Audio sink opened: %dHz, %dch, %d-bit, device=%s",
            sample_rate, channels, sample_width * 8,
            device_index if device_index is not None else "default",
        )

    def write(self, pcm_data: bytes) -> None:
        """Write PCM data to the virtual mic."""
        if self._stream is not None and self._stream.is_active():
            self._stream.write(pcm_data)

    def close(self) -> None:
        """Stop the stream and clean up virtual devices."""
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                logger.exception("Error closing audio stream")
            self._stream = None

        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

        self._destroy_virtual_sink()
        self._opened = False
        logger.info("Audio sink closed")

    def is_open(self) -> bool:
        return self._opened
