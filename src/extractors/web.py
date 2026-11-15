import logging
import re
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse
import httpx
import trafilatura
from bs4 import BeautifulSoup

from src.config import settings

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
}

CHALLENGE_PATTERNS = (
    "challenges.cloudflare.com",
    "cf-turnstile",
    "verifica connessione",
    "just a moment...",
    "attention required! | cloudflare",
    "checking your browser",
)


def is_bot_challenge(html: str) -> bool:
    """Verifica se il contenuto HTML corrisponde a una schermata di blocco anti-bot o Turnstile."""
    if not html or len(html) > 100000:
        return False
    lower = html.lower()
    return any(p in lower for p in CHALLENGE_PATTERNS)


def extract_slug_title(url: str) -> str:
    """Estrae un titolo human-readable dallo slug dell'URL se la pagina è inaccessibile o protetta."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path:
        return parsed.netloc
    parts = [p for p in path.split("/") if p]
    if not parts:
        return parsed.netloc
    slug = parts[-1]
    if slug.isdigit() or re.match(r"^n?\d+$", slug):
        slug = parts[-2] if len(parts) > 1 else slug
    slug = re.sub(r"\.(html?|php|asp[x]?)$", "", slug, flags=re.IGNORECASE)
    words = [w for w in re.split(r"[-_+]+", slug) if w and not w.isdigit()]
    if words:
        return " ".join(words).capitalize()
    return parsed.netloc


async def fetch_via_reader_bridge(url: str, timeout: Optional[float] = None) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """
    Fetches article content via r.jina.ai reader bridge, ideal for bypassing
    WAFs, Cloudflare/Varnish rate limits (429/403) and heavy scripts on public portals.
    Handles optional API keys and 401/402/429 bridge error codes.
    """
    bridge_timeout = timeout if timeout is not None else settings.JINA_TIMEOUT
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; PersonalAgent/1.0)",
    }
    if settings.JINA_API_KEY:
        headers["Authorization"] = f"Bearer {settings.JINA_API_KEY}"

    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=bridge_timeout) as client:
            resp = await client.get(jina_url)
            if resp.status_code in (401, 402, 429):
                logger.warning(
                    f"Bridge r.jina.ai responded with HTTP code {resp.status_code} for {url}. "
                    "Automatic fallback to URL slug extraction."
                )
                return None, resp.status_code

            if resp.status_code == 200:
                payload = None
                try:
                    payload = resp.json()
                except Exception as json_err:
                    logger.debug(f"r.jina.ai response not JSON parsable ({json_err}), attempting markdown/text fallback.")

                if isinstance(payload, dict):
                    data = payload.get("data")
                    if isinstance(data, dict):
                        title = (data.get("title") or "").strip()
                        content = (data.get("content") or "").strip()
                        if len(content) > 50:
                            clean_title = title or extract_slug_title(url)
                            return {
                                "source_type": "web_article",
                                "source_url": url,
                                "title": clean_title,
                                "raw_text": f"{clean_title}\n\n{content}",
                                "author": None,
                                "date": data.get("publishedTime"),
                                "extraction": {
                                    "tier": "bridge",
                                    "quality": "full",
                                    "http_status": 200,
                                },
                            }, 200

                # Resilient fallback: inspect plain text / markdown body
                text_body = resp.text.strip()
                quota_keywords = ("quota exceeded", "rate limit", "access denied", "payment required", "too many requests")
                if len(text_body) > 50 and not any(kw in text_body.lower() for kw in quota_keywords):
                    lines = text_body.splitlines()
                    title = ""
                    clean_lines = []
                    for line in lines:
                        if line.lower().startswith("title:") and not title:
                            title = line.split(":", 1)[1].strip()
                        elif not line.lower().startswith("url source:"):
                            clean_lines.append(line)
                    clean_content = "\n".join(clean_lines).strip()
                    if len(clean_content) > 50:
                        clean_title = title or extract_slug_title(url)
                        logger.info(f"Retrieved markdown article from r.jina.ai successfully for {url}")
                        return {
                            "source_type": "web_article",
                            "source_url": url,
                            "title": clean_title,
                            "raw_text": f"{clean_title}\n\n{clean_content}",
                            "author": None,
                            "date": None,
                            "extraction": {
                                "tier": "bridge",
                                "quality": "full",
                                "http_status": 200,
                            },
                        }, 200

                logger.warning(
                    f"Bridge r.jina.ai ha risposto con 200 ma payload privo di articolo valido (len={len(text_body)}). "
                    "Fallback automatico a estrazione slug."
                )
            return None, resp.status_code
    except Exception as e:
        logger.warning(f"Fallback reader bridge r.jina.ai fallito per {url}: {e}")
        return None, None


def parse_html_article(html_content: str, url: Optional[str] = None) -> Dict[str, Any]:
    """
    Estrae testo pulito e metadati da una stringa HTML usando trafilatura e fallback OpenGraph.
    """
    # 1. Tentativo con trafilatura (rimuove pubblicità, cookie banner, menu e footer)
    text = trafilatura.extract(
        html_content,
        url=url,
        include_links=False,
        include_images=False,
        output_format="txt",
    )

    metadata = trafilatura.extract_metadata(html_content, default_url=url)
    title = metadata.title if metadata and metadata.title else None
    author = metadata.author if metadata and metadata.author else None
    date = metadata.date if metadata and metadata.date else None

    # 2. Fallback su tag OpenGraph se il testo estratto è scarso
    is_partial = False
    if not text or len(text.strip()) < 50:
        is_partial = True
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Titolo
        if not title:
            og_title = soup.find("meta", property="og:title")
            title = og_title.get("content") if og_title else (soup.title.string if soup.title else None)

        # Descrizione
        og_desc = soup.find("meta", property="og:description")
        desc = og_desc.get("content") if og_desc else ""
        if not desc:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            desc = meta_desc.get("content") if meta_desc else ""

        paragraphs = [p.get_text().strip() for p in soup.find_all("p") if len(p.get_text().strip()) > 30]
        text = f"{desc}\n\n" + "\n\n".join(paragraphs) if paragraphs else desc

    clean_title = title.strip() if title else extract_slug_title(url or "")
    clean_text = text.strip() if text else clean_title
    quality = "partial" if is_partial else "full"

    return {
        "source_type": "web_article",
        "source_url": url or "",
        "title": clean_title,
        "raw_text": f"{clean_title}\n\n{clean_text}",
        "author": author,
        "date": date,
        "extraction": {
            "tier": "direct",
            "quality": quality,
            "http_status": 200,
        },
    }


async def extract_web_article(url: str, timeout: float = 12.0) -> Dict[str, Any]:
    """
    Scarica la pagina web ed estrae il contenuto principale pulito.
    Adotta una strategia a cascata a tre livelli:
    1. Download diretto (httpx + trafilatura)
    2. Reader Bridge (r.jina.ai) per aggirare 403, 429 o challenge Cloudflare/Turnstile
    3. Fallback semantico generato dallo slug e dal dominio dell'URL
    """
    logger.info(f"Scaricamento articolo web da: {url}")
    html: Optional[str] = None
    direct_failed = False
    direct_http_status: Optional[int] = None

    try:
        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url)
            direct_http_status = response.status_code
            if response.status_code in (403, 429, 503):
                logger.warning(f"Download diretto ha risposto con HTTP {response.status_code} su {url}. Attivazione reader bridge.")
                direct_failed = True
            else:
                response.raise_for_status()
                html = response.text
                if is_bot_challenge(html):
                    logger.warning(f"Rilevato anti-bot challenge su {url}. Attivazione reader bridge.")
                    direct_failed = True
                    html = None
    except Exception as e:
        logger.warning(f"Download diretto fallito per {url}: {e}. Tento con reader bridge.")
        direct_failed = True

    # Se il download diretto ha funzionato e ha contenuto valido, lo analizziamo
    if html and not direct_failed:
        article = parse_html_article(html, url=url)
        if len(article.get("raw_text", "").strip()) > 100:
            article["extraction"] = {
                "tier": "direct",
                "quality": "full",
                "http_status": direct_http_status or 200,
            }
            return article
        logger.info(f"Testo estratto con trafilatura scarso per {url}. Tentativo con reader bridge.")

    # 2. Tentativo con Reader Bridge (r.jina.ai)
    bridge_article, bridge_status = await fetch_via_reader_bridge(url)
    if bridge_article:
        logger.info(f"Articolo web estratto con successo tramite reader bridge da: {url}")
        return bridge_article

    # Se avevamo recuperato un html parziale (es. OpenGraph valido)
    if html:
        article = parse_html_article(html, url=url)
        article["extraction"] = {
            "tier": "direct",
            "quality": "partial",
            "http_status": direct_http_status or 200,
        }
        return article

    # 3. Fallback semantico su slug (senza frasi tecniche di errore in raw_text)
    slug_title = extract_slug_title(url)
    domain = urlparse(url).netloc
    logger.info(f"Uso fallback semantico basato su slug per {url}: '{slug_title}'")
    return {
        "source_type": "web_article",
        "source_url": url,
        "title": slug_title,
        "raw_text": f"Articolo web da {domain}: {slug_title}\nURL: {url}",
        "author": None,
        "date": None,
        "extraction": {
            "tier": "slug",
            "quality": "link_only",
            "http_status": direct_http_status or 429,
        },
    }
