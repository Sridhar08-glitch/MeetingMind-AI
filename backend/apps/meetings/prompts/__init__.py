"""Versioned prompt registry for AI analysis + chat."""
from .definitions import (
    ANALYSIS_VERSION,
    CHAT_VERSION,
    SPEAKER_NAMING_VERSION,
    analysis_schema,
    chat_schema,
)
from .registry import Prompt, prompt_registry, register_prompt

__all__ = [
    "Prompt", "prompt_registry", "register_prompt",
    "ANALYSIS_VERSION", "analysis_schema", "CHAT_VERSION", "chat_schema",
    "SPEAKER_NAMING_VERSION",
]
