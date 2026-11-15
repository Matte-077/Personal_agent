import io
import logging
import re
from typing import Optional
import edge_tts

logger = logging.getLogger(__name__)

# Default neural natural voices
DEFAULT_ITALIAN_VOICE = "it-IT-DiegoNeural"  # Clear natural Italian male voice
ALTERNATIVE_ITALIAN_VOICE = "it-IT-ElsaNeural"  # Natural Italian female voice


def clean_text_for_speech(text: str) -> str:
    """
    Strips HTML tags, links, emojis and formatting characters for text-to-speech synthesis.
    """
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", "", text)
    # Remove URLs
    clean = re.sub(r"https?://\S+", "", clean)
    # Remove bracketed labels or markdown links
    clean = re.sub(r"\[.*?\]", "", clean)
    # Remove markdown formatting characters
    clean = re.sub(r"[#*_~`━─=]", "", clean)
    # Remove unpronounceable emojis and pictographic symbols
    clean = re.sub(r"[\U00010000-\U0010ffff]", "", clean)
    clean = re.sub(r"[\u2600-\u27BF]", "", clean)
    # Compact whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


async def synthesize_speech(
    text: str,
    voice: str = DEFAULT_ITALIAN_VOICE,
    max_chars: int = 1200,
) -> Optional[bytes]:
    """
    Synthesizes text into audio MP3 via edge-tts (100% free, zero API keys required).
    Optimized for Telegram quick response voice notes (15-40s).
    If text exceeds max_chars, truncates on the last complete sentence to avoid overly long audio.
    """
    cleaned = clean_text_for_speech(text)
    if not cleaned:
        return None

    if len(cleaned) > max_chars:
        # Truncate on nearest sentence punctuation
        truncated = cleaned[:max_chars]
        last_period = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
        if last_period > 200:
            cleaned = truncated[:last_period + 1]
        else:
            cleaned = truncated + "..."

    try:
        communicate = edge_tts.Communicate(cleaned, voice=voice)
        audio_io = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio_io.write(chunk.get("data", b""))

        audio_bytes = audio_io.getvalue()
        if audio_bytes and len(audio_bytes) > 0:
            logger.info(f"TTS speech synthesis complete ({len(audio_bytes)} bytes).")
            return audio_bytes
        return None
    except Exception as e:
        logger.warning(f"Error during edge-tts speech synthesis: {e}")
        return None

