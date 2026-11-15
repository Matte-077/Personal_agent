import asyncio
import atexit
import logging
import os
import re
import stat
import tempfile
from typing import Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
import yt_dlp

from src.config import settings

logger = logging.getLogger(__name__)

# User-Agent che simulano crawler di anteprima social (Meta permette loro di leggere i tag OpenGraph)
CRAWLER_HEADERS = {
    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
}

COBALT_PUBLIC_INSTANCES = [
    "https://api.cobalt.tools/api/json",
    "https://cobalt.api.kwiatekm.tokyo/api/json",
]

# Pattern di errore yt-dlp che indicano cookie scaduti / login-wall di Meta.
COOKIE_EXPIRED_PATTERNS = (
    "login required",
    "not logged in",
    "session expired",
    "checkpoint",
    "confirm your age",
    "redirecting to /accounts/login",
    "/accounts/login/",
)

_COOKIEFILE_PATH: Optional[str] = None


def is_cookie_expired_error(message: str) -> bool:
    """Verifica se un messaggio di errore yt-dlp indica cookie scaduti o login-wall."""
    if not message:
        return False
    lower = message.lower()
    return any(p in lower for p in COOKIE_EXPIRED_PATTERNS)


def reset_instagram_cookiefile_cache() -> None:
    """Azzera la cache del cookiefile (usato nei test)."""
    global _COOKIEFILE_PATH
    _COOKIEFILE_PATH = None


def _remove_cookiefile(path: str) -> None:
    """Rimuove il cookiefile temporaneo all'uscita (evita accumuli in /tmp in locale)."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"Instagram cookiefile cleanup failed for {path}: {e}")


def ensure_instagram_cookiefile() -> Optional[str]:
    """
    Tier 1: Prepares Netscape cookie file for yt-dlp from burner account.

    Supports (in priority order):
    1. `INSTAGRAM_COOKIES` as an existing file path.
    2. `INSTAGRAM_COOKIES` as raw Netscape text exported from browser.
    3. `IG_SESSIONID` (+ optional `IG_CSRFTOKEN`, `IG_USER_ID`) to synthesize file.

    Temporary file is created with 0600 permissions. Returns None if unconfigured.
    """
    global _COOKIEFILE_PATH
    if _COOKIEFILE_PATH and os.path.exists(_COOKIEFILE_PATH):
        return _COOKIEFILE_PATH

    raw = (settings.INSTAGRAM_COOKIES or "").strip()
    if raw and os.path.exists(raw):
        _COOKIEFILE_PATH = raw
        return _COOKIEFILE_PATH

    content: Optional[str] = None
    if raw and "netscape" in raw.lower():
        content = raw if raw.endswith("\n") else raw + "\n"
    elif settings.IG_SESSIONID:
        lines = ["# Netscape HTTP Cookie File"]
        lines.append(
            f".instagram.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\t{settings.IG_SESSIONID.strip()}"
        )
        if settings.IG_CSRFTOKEN:
            lines.append(
                f".instagram.com\tTRUE\t/\tTRUE\t2147483647\tcsrftoken\t{settings.IG_CSRFTOKEN.strip()}"
            )
        if settings.IG_USER_ID:
            lines.append(
                f".instagram.com\tTRUE\t/\tTRUE\t2147483647\tds_user_id\t{settings.IG_USER_ID.strip()}"
            )
        content = "\n".join(lines) + "\n"

    if not content:
        if raw:
            logger.warning(
                "INSTAGRAM_COOKIES non è un percorso file valido né contenuto "
                "Netscape: cookie Instagram ignorati."
            )
        return None

    try:
        fd, path = tempfile.mkstemp(prefix="ig_cookies_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        atexit.register(_remove_cookiefile, path)
        _COOKIEFILE_PATH = path
        logger.info("Cookiefile Instagram preparato per yt-dlp (Metodo 1).")
        return path
    except Exception as e:
        logger.warning(f"Impossibile creare il cookiefile Instagram: {e}")
        return None


def clean_instagram_url(url: str) -> str:
    """Rimuove parametri di tracking (es. ?igsh=...) dall'URL del post o reel."""
    clean = re.sub(r"\?.*$", "", url.strip())
    return clean.rstrip("/")


def parse_instagram_opengraph_html(html_content: str, url: str) -> Optional[Dict[str, Any]]:
    """
    Estrae metadati, titolo e didascalia (caption) dai tag OpenGraph HTML.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    og_desc = soup.find("meta", property="og:description")
    og_title = soup.find("meta", property="og:title")
    og_image = soup.find("meta", property="og:image")
    og_video = soup.find("meta", property="og:video") or soup.find("meta", property="og:video:secure_url")

    caption = og_desc.get("content") if og_desc else ""
    title = og_title.get("content") if og_title else "Instagram Reel"
    media_url = og_video.get("content") if og_video else (og_image.get("content") if og_image else None)

    if caption or title:
        raw_text = f"Instagram Post/Reel: {title}\n\nDidascalia / Caption:\n{caption}"
        return {
            "source_type": "instagram",
            "source_url": url,
            "title": title,
            "raw_text": raw_text,
            "caption": caption,
            "media_url": media_url,
            "tier_used": "tier_2_opengraph",
            "extraction": {
                "tier": "direct",
                "quality": "partial",
                "http_status": 200,
            },
        }
    return None


def _sync_ytdlp_extract(url: str) -> Optional[Dict[str, Any]]:
    """Estrazione sincrona isolata per yt-dlp con timeout socket ed eventuali cookie burner."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "socket_timeout": 8,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            ),
        },
    }

    cookiefile = ensure_instagram_cookiefile()
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            title = info.get("title") or "Instagram Reel"
            description = info.get("description") or ""
            uploader = info.get("uploader") or ""
            video_url = info.get("url")
            if not video_url and info.get("formats"):
                for f in reversed(info["formats"]):
                    if f.get("url") and f.get("vcodec") != "none":
                        video_url = f["url"]
                        break

            raw_text = f"Instagram Reel di @{uploader}: {title}\n\nDidascalia / Caption:\n{description}"

            return {
                "source_type": "instagram",
                "source_url": url,
                "title": title,
                "raw_text": raw_text,
                "caption": description,
                "media_url": video_url,
                "uploader": uploader,
                "tier_used": "tier_1_ytdlp",
                "extraction": {
                    "tier": "direct",
                    "quality": "full",
                    "http_status": 200,
                },
            }
    except Exception as e:
        err_msg = str(e)
        if is_cookie_expired_error(err_msg):
            logger.error(
                "🚨 Cookie Instagram scaduti o invalidati da Meta! "
                "Rinnova IG_SESSIONID / INSTAGRAM_COOKIES nelle impostazioni."
            )
            return {"cookie_expired": True, "error": err_msg, "source_url": url}
        logger.debug(f"yt-dlp ha fallito l'estrazione da {url}: {e}")
        return None


async def extract_with_ytdlp(url: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """
    Tier 1: Esecuzione non-bloccante di yt-dlp in un thread separato con timeout perentorio.
    """
    try:
        return await asyncio.wait_for(asyncio.to_thread(_sync_ytdlp_extract, url), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"yt-dlp timeout dopo {timeout}s per {url}")
        return None
    except Exception as e:
        logger.warning(f"Errore asincrono yt-dlp per {url}: {e}")
        return None


async def extract_with_opengraph_crawler(url: str, timeout: float = 8.0) -> Optional[Dict[str, Any]]:
    """
    Tier 2: Richiesta HTTP con header da crawler social per estrarre la didascalia completa.
    """
    try:
        async with httpx.AsyncClient(headers=CRAWLER_HEADERS, follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return parse_instagram_opengraph_html(resp.text, url)
    except Exception as e:
        logger.debug(f"OpenGraph crawler fallito per {url}: {e}")
    return None


async def extract_with_rapidapi_bridge(url: str, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """
    Tier 3A (Metodo 3): Instagram Scraper via RapidAPI (free tier).
    Richiede RAPIDAPI_KEY; host configurabile via RAPIDAPI_INSTAGRAM_HOST.
    L'onere del bypass anti-bot grava sul provider esterno.
    """
    api_key = (settings.RAPIDAPI_KEY or "").strip()
    if not api_key:
        return None

    host = (settings.RAPIDAPI_INSTAGRAM_HOST or "").strip()
    timeout_s = timeout if timeout is not None else settings.INSTAGRAM_TIMEOUT
    headers = {
        "Accept": "application/json",
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": host,
    }
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=timeout_s) as client:
            resp = await client.get(f"https://{host}/v1/post_info", params={"url": url})
            if resp.status_code in (401, 402, 403, 429):
                logger.warning(
                    f"RapidAPI Instagram ha risposto con HTTP {resp.status_code} per {url}."
                )
                return None
            if resp.status_code != 200:
                return None
            payload = resp.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                data = payload if isinstance(payload, dict) else {}

            caption = ""
            cap = data.get("caption")
            if isinstance(cap, dict):
                caption = cap.get("text") or ""
            elif isinstance(cap, str):
                caption = cap
            caption = caption or data.get("text") or ""

            media_url = (
                data.get("video_url")
                or data.get("media_url")
                or data.get("url")
                or data.get("thumbnail_url")
            )
            owner = data.get("owner") or data.get("user") or {}
            uploader = owner.get("username", "") if isinstance(owner, dict) else ""
            title = data.get("title") or (f"Instagram Reel di @{uploader}" if uploader else "Instagram Reel")

            if media_url or caption:
                return {
                    "source_type": "instagram",
                    "source_url": url,
                    "title": title,
                    "raw_text": f"{title}\n\nDidascalia / Caption:\n{caption}" if caption else f"{title} (video estratto)",
                    "caption": caption,
                    "media_url": media_url,
                    "uploader": uploader,
                    "tier_used": "tier_3_rapidapi",
                    "extraction": {
                        "tier": "bridge",
                        "quality": "full",
                        "http_status": 200,
                    },
                }
    except Exception as e:
        logger.debug(f"RapidAPI Instagram bridge fallito per {url}: {e}")
    return None


async def extract_with_cobalt_bridge(url: str, timeout: float = 8.0) -> Optional[Dict[str, Any]]:
    """
    Tier 3: Fallback su API bridge multimediale Cobalt.
    """
    payload = {"url": url}
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    for endpoint in COBALT_PUBLIC_INSTANCES:
        try:
            async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
                resp = await client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    media_url = data.get("url")
                    text = data.get("text") or data.get("caption") or ""
                    if media_url or text:
                        return {
                            "source_type": "instagram",
                            "source_url": url,
                            "title": "Instagram Reel",
                            "raw_text": f"Instagram Reel:\n{text}" if text else "Instagram Reel (video estratto)",
                            "caption": text,
                            "media_url": media_url,
                            "tier_used": "tier_3_bridge",
                            "extraction": {
                                "tier": "bridge",
                                "quality": "full",
                                "http_status": 200,
                            },
                        }
        except Exception as e:
            logger.debug(f"Bridge {endpoint} non disponibile: {e}")

    return None


async def extract_instagram_content(url: str) -> Dict[str, Any]:
    """
    Pipeline multi-livello per l'estrazione di Instagram Reels:
    1. yt-dlp (con cookie burner Netscape se configurati - Metodo 1)
    2. OpenGraph Crawler
    3A. RapidAPI Instagram Scraper (se RAPIDAPI_KEY configurata - Metodo 3)
    3B. Media Bridge Cobalt (mirror multipli)
    4. Fallback assistito trasparente
    """
    clean_url = clean_instagram_url(url)
    logger.info(f"Avvio pipeline Instagram per: {clean_url}")
    cookie_expired = False

    # Livello 1: yt-dlp (autenticato se cookie burner disponibili)
    res = await extract_with_ytdlp(clean_url)
    if res and res.get("cookie_expired"):
        cookie_expired = True
        res = None
    if res and res.get("caption"):
        logger.info("Instagram estratto con successo tramite Tier 1 (yt-dlp).")
        return res

    # Livello 2: OpenGraph Crawler
    res = await extract_with_opengraph_crawler(clean_url)
    if res and res.get("caption"):
        logger.info("Instagram estratto con successo tramite Tier 2 (OpenGraph).")
        if cookie_expired:
            res["cookie_expired"] = True
        return res

    # Livello 3A: RapidAPI Instagram Scraper.
    # Nota: a differenza di Tier 1/2 (che richiedono caption), qui basta `if res`
    # anche con solo video_url e caption vuota: il file MP4 da solo sblocca
    # comunque l'analisi multimodale Gemini, quindi è utile salvarlo.
    res = await extract_with_rapidapi_bridge(clean_url)
    if res:
        logger.info("Instagram estratto con successo tramite Tier 3A (RapidAPI).")
        if cookie_expired:
            res["cookie_expired"] = True
        return res

    # Livello 3B: Cobalt Bridge
    res = await extract_with_cobalt_bridge(clean_url)
    if res:
        logger.info("Instagram estratto con successo tramite Tier 3B (Cobalt).")
        if cookie_expired:
            res["cookie_expired"] = True
        return res

    # Livello 4: Fallback Trasparente
    logger.warning(f"Tutti i livelli di estrazione Instagram hanno fallito per: {clean_url}")
    fallback_text = (
        f"Reel Instagram ({clean_url})\n\n"
        "I blocchi di protezione di Meta hanno impedito l'estrazione automatica della didascalia. "
        "Se vuoi salvare questo contenuto, puoi incollare il testo della ricetta/post o inoltrare il video direttamente qui."
    )
    return {
        "source_type": "instagram",
        "source_url": clean_url,
        "title": "Instagram Reel",
        "raw_text": fallback_text,
        "caption": "",
        "media_url": None,
        "tier_used": "tier_4_fallback",
        "cookie_expired": cookie_expired,
        "extraction": {
            "tier": "fallback",
            "quality": "link_only",
            "http_status": 403,
        },
    }
