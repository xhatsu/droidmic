"""Abstract base class for platform-specific audio sinks.

An audio sink receives raw PCM audio data and writes it to a virtual
audio device so that other applications can use it as a microphone input.
"""

import abc


class AudioSink(abc.ABC):
    """Base class for audio output to a virtual microphone device."""

    @abc.abstractmethod
    def open(self, sample_rate: int, channels: int, sample_width: int) -> None:
        """Initialize the audio sink and prepare for writing.

        Args:
            sample_rate: Sample rate in Hz (e.g., 44100).
            channels: Number of audio channels (1 = mono).
            sample_width: Bytes per sample (2 = 16-bit).
        """

    @abc.abstractmethod
    def write(self, pcm_data: bytes) -> None:
        """Write raw PCM audio data to the virtual device.

        Args:
            pcm_data: Raw PCM audio bytes (little-endian, signed).
        """

    @abc.abstractmethod
    def close(self) -> None:
        """Release resources and close the audio device."""

    @abc.abstractmethod
    def is_open(self) -> bool:
        """Return True if the sink is currently open and writable."""
