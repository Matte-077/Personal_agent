"""
AI module for structured classification with Gemini / Ollama and vector embeddings.
"""

from src.ai.prompts import ItemClassification, CategoryEnum
from src.ai.gemini_client import GeminiClient

__all__ = ["GeminiClient", "ItemClassification", "CategoryEnum"]
