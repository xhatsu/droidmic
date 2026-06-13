"""Windows audio sink using VB-Cable (or similar virtual audio cable).

Writes PCM audio to the VB-Cable input device via PyAudio.
The user must install VB-Cable (https://vb-audio.com/Cable/) separately.
Applications then select "CABLE Output" as their microphone input.
"""

import logging

import pyaudio

from audio_sink import AudioSink

logger = logging.getLogger(__name__)

# Common names for virtual audio cable input devices
_CABLE_DEVICE_NAMES = [
    "CABLE Input",          # VB-Cable default
    "cable input",
    "VB-Audio Virtual Cable",
    "virtual cable",
]


class WindowsAudioSink(AudioSink):
    """Writes PCM audio to VB-Cable input on Windows."""

    def __init__(self) -> None:
        self._pa: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None
        self._opened = False

    def _find_cable_device(self) -> int | None:
        """Search for VB-Cable input device index."""
        if self._pa is None:
            return None

        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            name = info.get("name", "").lower()
            if any(cable.lower() in name for cable in _CABLE_DEVICE_NAMES):
                if info.get("maxOutputChannels", 0) > 0:
                    logger.info("Found VB-Cable device: %s (index %d)", info["name"], i)
                    return i
        return None

    def open(self, sample_rate: int, channels: int, sample_width: int) -> None:
        if self._opened:
            return

        self._pa = pyaudio.PyAudio()
        device_index = self._find_cable_device()

        if device_index is None:
            logger.warning(
                "VB-Cable device not found. Audio will play to default output.\n"
                "Install VB-Cable from https://vb-audio.com/Cable/ to create "
                "a virtual microphone."
            )

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
            "Windows audio sink opened: %dHz, %dch, %d-bit, device=%s",
            sample_rate, channels, sample_width * 8,
            device_index if device_index is not None else "default",
        )

    def write(self, pcm_data: bytes) -> None:
        if self._stream is not None and self._stream.is_active():
            self._stream.write(pcm_data)

    def close(self) -> None:
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

        self._opened = False
        logger.info("Windows audio sink closed")

    def is_open(self) -> bool:
        return self._opened
