import logging
import re
import uuid
from typing import List
import httpx

from src.utils.image_compressor import compress_image_to_webp
from src.db.storage import upload_car_photo

logger = logging.getLogger(__name__)


MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB limit


def parse_requested_photo_indices(text: str, total_available: int = 20) -> List[int]:
    """
    Riconosce se l'utente richiede foto specifiche dell'annuncio:
    - 'foto 2/16 e 3/16' -> [1, 2] (0-indexed)
    - 'foto 2 e 5' -> [1, 4]
    - 'foto 1, 4' -> [0, 3]
    - 'foto 3' -> [2]
    - 'foto 2/18' -> [1]

    Se non viene specificato nulla nel testo, restituisce di default le prime 2 foto: [0, 1].
    Garantisce che gli indici siano validi rispetto a total_available (senza duplicati o out of bounds).
    """
    if not text:
        return [0, min(1, max(0, total_available - 1))] if total_available > 0 else []

    photo_section = re.search(r'\bfot(?:o|e|i)\b\s*([0-9\/\s,e\-\+]+)', text, re.IGNORECASE)
    extracted_indices = []

    if photo_section:
        sub = photo_section.group(1)
        matches = re.findall(r'\b(\d+)(?:\/\d+)?\b', sub)
        for m in matches:
            idx_1_based = int(m)
            idx_0_based = idx_1_based - 1
            if 0 <= idx_0_based < total_available and idx_0_based not in extracted_indices:
                extracted_indices.append(idx_0_based)

    if extracted_indices:
        return extracted_indices[:2]

    if total_available <= 0:
        return []
    elif total_available == 1:
        return [0]
    else:
        return [0, 1]


async def process_and_upload_car_photos(
    available_images: List[str],
    user_text: str = "",
    user_id: str = "default",
    timeout: float = 10.0,
) -> List[str]:
    """
    Downloads selected vehicle images (first 2 by default or those requested by user e.g. 'photo 2/16 and 3/16'),
    validates headers (Content-Length, Content-Type), compresses to WebP, and uploads to Storage.
    Returns list of public uploaded URLs.
    """
    if not available_images:
        return []

    indices = parse_requested_photo_indices(user_text, total_available=len(available_images))
    if not indices:
        return []

    uploaded_urls: List[str] = []

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for idx in indices:
            img_url = available_images[idx]
            try:
                logger.info(f"Downloading car photo #{idx+1}: {img_url}")
                # Stream check Content-Length & Content-Type before reading full body
                async with client.stream("GET", img_url) as resp:
                    if resp.status_code != 200:
                        logger.warning(f"Car photo #{idx+1} download failed with status {resp.status_code}")
                        continue

                    c_len = resp.headers.get("Content-Length")
                    if c_len and int(c_len) > MAX_IMAGE_SIZE:
                        logger.warning(f"Car photo #{idx+1} rejected: excessive size ({c_len} bytes)")
                        continue

                    c_type = resp.headers.get("Content-Type", "")
                    if c_type and not any(t in c_type.lower() for t in ("image/", "octet-stream")):
                        logger.warning(f"Car photo #{idx+1} rejected: invalid Content-Type ({c_type})")
                        continue

                    raw_bytes = await resp.aread()

                if len(raw_bytes) > MAX_IMAGE_SIZE:
                    logger.warning(f"Foto #{idx+1} scartata: peso superiore al limite ({len(raw_bytes)} bytes)")
                    continue

                compressed_webp = compress_image_to_webp(raw_bytes, max_size=(1024, 768), quality=75)
                if not compressed_webp:
                    logger.warning(f"Foto #{idx+1} scartata: compressione fallita (file corrotto)")
                    continue

                fname = f"car_{uuid.uuid4().hex[:8]}_p{idx+1}.webp"
                public_url = upload_car_photo(compressed_webp, filename=fname, user_id=user_id)
                if public_url:
                    uploaded_urls.append(public_url)
            except Exception as e:
                logger.warning(f"Errore download/compressione foto #{idx+1} ({img_url}): {e}")

    return uploaded_urls
