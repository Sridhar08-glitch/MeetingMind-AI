"""Config-selected local translation providers (Phase 13)."""
from .base import TranslationProvider, TranslationResult
from .dummy import DummyTranslationProvider
from .factory import get_translation_provider

__all__ = [
    "TranslationProvider",
    "TranslationResult",
    "DummyTranslationProvider",
    "get_translation_provider",
]
