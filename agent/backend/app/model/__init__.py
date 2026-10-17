"""Model provider package for EVA Agent Backend."""

from app.model.base import ModelEvent, ModelEventType, ModelProvider, ModelProviderError
from app.model.ollama import OllamaProvider
from app.model.scripted import ScriptedProvider

__all__ = [
    "ModelEvent",
    "ModelEventType",
    "ModelProvider",
    "ModelProviderError",
    "OllamaProvider",
    "ScriptedProvider",
]
