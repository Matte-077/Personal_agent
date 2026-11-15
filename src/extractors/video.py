import asyncio
import logging
import re
from typing import Dict, Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from src.extractors.instagram import (
    extract_instagram_content,
    extract_with_ytdlp,
    extract_with_cobalt_bridge,
    extract_with_opengraph_crawler,
    CRAWLER_HEADERS,
)

logger = logging.getLogger(__name__)


def clean_video_url(url: str) -> str:
    """Strips tracking parameters (e.g. ?si=..., ?igsh=..., ?utm_...) from video URLs."""
    clean = re.sub(r"\?.*$", "", url.strip())
    return clean.rstrip("/")


def detect_video_platform(url: str) -> str:
    """Identifies specific video platform from URL."""
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
    return "other"


def parse_generic_video_opengraph(html_content: str, url: str, platform: str) -> Optional[Dict[str, Any]]:
    """Extracts generic OpenGraph metadata for video URLs (YouTube Shorts, TikTok)."""
    soup = BeautifulSoup(html_content, "html.parser")
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_video = (
        soup.find("meta", property="og:video")
        or soup.find("meta", property="og:video:secure_url")
        or soup.find("meta", property="og:video:url")
    )

    title_val = og_title.get("content") if og_title else ""
    desc_val = og_desc.get("content") if og_desc else ""
    video_url = og_video.get("content") if og_video else None

    platform_label = "YouTube Shorts" if "youtube" in platform else ("TikTok" if platform == "tiktok" else "Video")

    if title_val or desc_val:
        title = title_val or f"Video {platform_label}"
        raw_text = f"{platform_label}: {title}\n\nCaption / Description:\n{desc_val}"
        return {
            "source_type": "other",
            "is_video": True,
            "video_platform": platform,
            "source_url": url,
            "title": title,
            "raw_text": raw_text,
            "caption": desc_val,
            "media_url": video_url,
            "tier_used": "tier_2_opengraph",
            "extraction": {
                "tier": "direct",
                "quality": "partial",
                "http_status": 200,
            },
        }
    return None


async def extract_video_content(url: str, platform: Optional[str] = None) -> Dict[str, Any]:
    """
    Universal short-form video extractor:
    Supports Instagram Reels, TikTok, and YouTube Shorts.
    
    Cascaded fallback strategy:
    1. yt-dlp (MP4 video stream and full metadata)
    2. OpenGraph Crawler (title and caption recovery)
    3. Cobalt Media Bridge
    4. Transparent assisted fallback
    """
    clean_url = clean_video_url(url)
    target_platform = platform or detect_video_platform(clean_url)

    if target_platform == "instagram":
        res = await extract_instagram_content(clean_url)
        res["is_video"] = True
        res["video_platform"] = "instagram"
        return res

    platform_name = "TikTok" if target_platform == "tiktok" else "YouTube Shorts"
    logger.info(f"Starting {platform_name} video pipeline for: {clean_url}")

    # Tier 1: yt-dlp
    try:
        res = await extract_with_ytdlp(clean_url)
        if res and (res.get("caption") or res.get("media_url") or res.get("title")):
            logger.info(f"{platform_name} extracted successfully via Tier 1 (yt-dlp).")
            # Supabase items table accepts 'source_type' matching CHECK constraint
            res["source_type"] = "other"
            res["is_video"] = True
            res["video_platform"] = target_platform
            return res
    except Exception as e:
        logger.debug(f"yt-dlp failed for {platform_name} {clean_url}: {e}")

    # Tier 2: OpenGraph Crawler
    try:
        async with httpx.AsyncClient(headers=CRAWLER_HEADERS, follow_redirects=True, timeout=8.0) as client:
            resp = await client.get(clean_url)
            if resp.status_code == 200:
                og_res = parse_generic_video_opengraph(resp.text, clean_url, target_platform)
                if og_res:
                    logger.info(f"{platform_name} extracted successfully via Tier 2 (OpenGraph).")
                    return og_res
    except Exception as e:
        logger.debug(f"OpenGraph crawler failed for {platform_name} {clean_url}: {e}")

    # Tier 3: Cobalt Bridge
    try:
        res = await extract_with_cobalt_bridge(clean_url)
        if res:
            logger.info(f"{platform_name} extracted successfully via Tier 3 (Cobalt).")
            res["source_type"] = "other"
            res["is_video"] = True
            res["video_platform"] = target_platform
            res["title"] = f"{platform_name} Video"
            return res
    except Exception as e:
        logger.debug(f"Cobalt bridge failed for {platform_name} {clean_url}: {e}")

    # Tier 4: Transparent fallback
    logger.warning(f"All extraction tiers failed for {platform_name}: {clean_url}")
    fallback_text = (
        f"Video {platform_name} ({clean_url})\n\n"
        f"Could not automatically extract video stream or details for this {platform_name}. "
        "You can save a note or forward the video directly to this chat for transcription."
    )
    return {
        "source_type": "other",
        "is_video": True,
        "video_platform": target_platform,
        "source_url": clean_url,
        "title": f"Video {platform_name}",
        "raw_text": fallback_text,
        "caption": "",
        "media_url": None,
        "tier_used": "tier_4_fallback",
        "extraction": {
            "tier": "fallback",
            "quality": "link_only",
            "http_status": 403,
        },
    }

