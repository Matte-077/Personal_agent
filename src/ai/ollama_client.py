import json
import logging
from typing import Optional, List, Dict, Any
import httpx

from src.config import settings
from src.ai.prompts import ItemClassification, SYSTEM_PROMPT
from src.ai.gemini_client import sanitize_text_for_ai

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Client for interacting with a local Ollama server (100% offline and private).
    Supports:
    - Structured JSON classification with local LLMs (e.g. llama3.2, mistral, qwen2.5)
    - Local vector embeddings generation (e.g. nomic-embed-text, all-minilm)
    - Local consultative answers
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        embedding_model: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.embedding_model = embedding_model or settings.OLLAMA_EMBEDDING_MODEL
        self.timeout = timeout
        self.http_client = httpx.Client(timeout=self.timeout)

    def is_available(self) -> bool:
        """Quickly checks whether the local Ollama server is running."""
        try:
            res = self.http_client.get(f"{self.base_url}/api/tags", timeout=3.0)
            return res.status_code == 200
        except Exception:
            return False

    def classify_content(
        self,
        raw_text: str,
        source_type: str = "text_note",
        quality: str = "full",
    ) -> ItemClassification:
        """
        Classifies and structures text querying Ollama in structured JSON mode.
        """
        cleaned_text = sanitize_text_for_ai(raw_text) if quality != "full" else raw_text
        user_prompt = (
            f"Content source: {source_type}\n"
            f"Extraction quality: {quality}\n"
            f"Text to analyze and catalogue:\n\"\"\"\n{cleaned_text}\n\"\"\"\n\n"
            "Respond solely with valid JSON conforming to the specified schema."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2},
        }

        logger.info(f"[Ollama] Requesting JSON classification from {self.base_url} with model {self.model}")
        try:
            res = self.http_client.post(f"{self.base_url}/api/chat", json=payload)
            res.raise_for_status()
            data = res.json()
            content_str = data.get("message", {}).get("content", "").strip()

            return ItemClassification.model_validate_json(content_str)
        except Exception as e:
            logger.error(f"[Ollama] Classification error with Ollama: {e}")
            raise ValueError(f"Ollama classification failed: {e}")

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generates vector embedding for input text using the specified Ollama embedding model.
        Guarantees standardized 768-float dimensions (padding or truncating if needed).
        """
        logger.info(f"[Ollama] Generating embedding with {self.embedding_model}")
        payload = {
            "model": self.embedding_model,
            "prompt": text,
        }

        try:
            res = self.http_client.post(f"{self.base_url}/api/embeddings", json=payload)
            res.raise_for_status()
            data = res.json()
            vec = data.get("embedding")
            if not vec or not isinstance(vec, list):
                raise ValueError("Ollama response missing embedding vector")

            # Standardize to 768 float dimensions
            if len(vec) == 768:
                return vec
            elif len(vec) > 768:
                return vec[:768]
            else:
                return vec + [0.0] * (768 - len(vec))
        except Exception as e:
            logger.error(f"[Ollama] Embedding generation error with Ollama: {e}")
            raise ValueError(f"Ollama embedding generation failed: {e}")

    def generate_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
        """Generates textual response for consultation queries."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        res = self.http_client.post(f"{self.base_url}/api/chat", json=payload)
        res.raise_for_status()
        return res.json().get("message", {}).get("content", "").strip()

    def process_item(
        self,
        raw_text: str,
        source_type: str = "text_note",
        source_url: Optional[str] = None,
        user_id: str = "default",
        extraction: Optional[Dict[str, Any]] = None,
        quality: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Unified local Ollama ingestion pipeline:
        1. Classify raw text into structured schema
        2. Compute vector embedding on synthesized semantic summary
        3. Return database-ready record dictionary.
        """
        q = quality or (extraction.get("quality") if extraction else "full") or "full"

        classification = self.classify_content(raw_text=raw_text, source_type=source_type, quality=q)

        if q == "link_only":
            embedding = None
        else:
            text_to_embed = classification.embedding_text or f"{classification.title} {classification.summary}"
            text_to_embed = sanitize_text_for_ai(text_to_embed)
            embedding = self.generate_embedding(text_to_embed)

        metadata_dict = classification.metadata.model_dump(exclude_none=True)
        if extraction:
            metadata_dict["extraction"] = extraction

        confidence = float(classification.confidence)
        if q == "link_only" and confidence > 0.50:
            confidence = 0.50
        elif q == "partial" and confidence > 0.75:
            confidence = 0.75

        clean_raw = sanitize_text_for_ai(raw_text) if q != "full" else raw_text

        return {
            "user_id": user_id,
            "status": "active",
            "source_url": source_url,
            "source_type": source_type,
            "raw_text": clean_raw,
            "category": classification.category.value,
            "subcategory": classification.subcategory,
            "title": classification.title,
            "summary": classification.summary,
            "tags": classification.tags,
            "metadata": metadata_dict,
            "confidence": round(confidence, 2),
            "embedding": embedding,
        }

