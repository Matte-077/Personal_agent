import re
from typing import Dict, Any
from urllib.parse import urlparse

from src.extractors.web import extract_web_article
from src.extractors.mobile_de import extract_mobile_de
from src.extractors.instagram import extract_instagram_content
from src.extractors.video import extract_video_content, detect_video_platform

__all__ = [
    "extract_from_url",
    "detect_url_type",
    "extract_web_article",
    "extract_mobile_de",
    "extract_instagram_content",
    "extract_video_content",
]


def detect_url_type(url: str) -> str:
    """
    Detects link category from domain and URL path.
    Returns:
    - 'instagram', 'tiktok', 'youtube_shorts', 'youtube' (video)
    - 'mobile_de' (automotive)
    - 'web_article' (general web articles & news)
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()

    if "instagram.com" in domain or "instagr.am" in domain:
        return "instagram"
    elif "tiktok.com" in domain:
        return "tiktok"
    elif "youtube.com" in domain or "youtu.be" in domain:
        if "/shorts" in path or "youtu.be" in domain:
            return "youtube_shorts"
        return "youtube"
    elif "mobile.de" in domain:
        return "mobile_de"
    return "web_article"


async def extract_from_url(url: str) -> Dict[str, Any]:
    """
    Unified router: detects URL type and invokes
    the most appropriate specialized extractor.
    """
    url_type = detect_url_type(url)

    if url_type in ("instagram", "tiktok", "youtube_shorts", "youtube"):
        return await extract_video_content(url, platform=url_type)
    elif url_type == "mobile_de":
        return await extract_mobile_de(url)
    else:
        return await extract_web_article(url)
