import logging
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types

from src.config import settings
from src.ai.prompts import ItemClassification, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


INSTRUCTION_PATTERNS = [
    r"I blocchi di protezione di Meta hanno impedito l'estrazione automatica.*?(?:\n|$)",
    r"Se vuoi salvare questo contenuto, puoi incollare il testo.*?(?:\n|$)",
    r"incolla qui il testo.*?(?:\n|$)",
    r"La pagina ha attivato la protezione WAF.*?(?:\n|$)",
    r"Nota:.*?protezione WAF.*?(?:\n|$)",
    r"download non completato.*?(?:\n|$)",
]


def sanitize_text_for_ai(text: str) -> str:
    """
    Removes operational instruction phrases (e.g. paste text, WAF blocks, HTTP errors)
    to prevent polluting Gemini classification prompts and dense vector embeddings.
    """
    if not text:
        return ""
    import re
    cleaned = text
    for pattern in INSTRUCTION_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


class GeminiClient:
    """
    Client for Google Gemini APIs (Gemini Flash Lite and Text Embeddings).
    Handles structured JSON classification and 768-dimension vectorization.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured.")
        self.client = genai.Client(api_key=self.api_key)

    def classify_content(
        self,
        raw_text: str,
        source_type: str = "text_note",
        quality: str = "full",
    ) -> ItemClassification:
        """
        Analyzes and catalogues text, notes, or link metadata
        using Gemini Flash Lite with constrained JSON schema.
        If quality != 'full', sanitizes text from instructions and adds partial extraction note.
        """
        cleaned_text = sanitize_text_for_ai(raw_text) if quality != "full" else raw_text
        if quality != "full":
            prompt = (
                f"Origine contenuto: {source_type}\n"
                "Nota estrazione parziale: classifica da slug/URL, abbassa confidence, non inventare dettagli.\n"
                f"Testo da analizzare e catalogare:\n\"\"\"\n{cleaned_text}\n\"\"\""
            )
        else:
            prompt = (
                f"Origine contenuto: {source_type}\n"
                f"Testo da analizzare e catalogare:\n\"\"\"\n{cleaned_text}\n\"\"\""
            )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=ItemClassification,
        )

        logger.info(f"Classifying content with model: {settings.GEMINI_MODEL} (quality={quality})")
        
        # Automatic backoff retry to handle transient 503/429 spikes
        last_err = None
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                )

                if response.parsed and isinstance(response.parsed, ItemClassification):
                    return response.parsed

                if response.text:
                    return ItemClassification.model_validate_json(response.text)

            except Exception as e:
                last_err = e
                logger.warning(f"Classification attempt {attempt + 1}/3 failed ({e}). Retrying...")
                import time
                time.sleep(1.5 * (attempt + 1))

        raise ValueError(f"Classification failed after 3 attempts: {last_err}")

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generates semantic vector embedding forced to 768 float dimensions
        to guarantee 1:1 match with database schema (pgvector).
        """
        logger.info(f"Generating vector embedding (768-dim) with: {settings.GEMINI_EMBEDDING_MODEL}")
        
        last_err = None
        for attempt in range(3):
            try:
                res = self.client.models.embed_content(
                    model=settings.GEMINI_EMBEDDING_MODEL,
                    contents=text,
                    config=types.EmbedContentConfig(output_dimensionality=768),
                )

                if res.embeddings and res.embeddings[0].values:
                    embedding = res.embeddings[0].values
                    if len(embedding) == 768:
                        return embedding
                    else:
                        raise ValueError(f"Unexpected embedding dimension: {len(embedding)} instead of 768")
                else:
                    raise ValueError("Embedding API response missing vector values")
            except Exception as e:
                last_err = e
                logger.warning(f"Embedding attempt {attempt + 1}/3 failed ({e}). Retrying...")
                import time
                time.sleep(1.5 * (attempt + 1))

        raise ValueError(f"Embedding generation failed after 3 attempts: {last_err}")

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
        Unified pipeline:
        1. Classify raw text into structured card schema
        2. Compute vector embedding on sanitized semantic text
        3. Return database-ready record dictionary.
        """
        q = quality or (extraction.get("quality") if extraction else "full") or "full"

        # 1. Classification
        classification = self.classify_content(raw_text=raw_text, source_type=source_type, quality=q)

        # 2. Vector embedding calculated on cleaned text (skipped for link_only cards)
        if q == "link_only":
            logger.info("link_only extraction: skipping embedding (stored with embedding=None)")
            embedding = None
        else:
            text_to_embed = classification.embedding_text or f"{classification.title} {classification.summary}"
            text_to_embed = sanitize_text_for_ai(text_to_embed)
            embedding = self.generate_embedding(text_to_embed)

        # 3. Metadata cleaned of None fields and enriched with extraction info
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
