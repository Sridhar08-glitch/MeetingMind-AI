"""Speech-to-Text provider abstraction."""
from .base import STTResult, STTSegment, STTWord, SpeechToTextProvider
from .dummy import DummySpeechProvider
from .factory import get_speech_provider

__all__ = [
    "SpeechToTextProvider", "STTResult", "STTSegment", "STTWord",
    "DummySpeechProvider", "get_speech_provider",
]
