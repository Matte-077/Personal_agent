import io
import logging
from typing import Tuple, Optional
from PIL import Image

logger = logging.getLogger(__name__)


def compress_image_to_webp(
    image_bytes: bytes,
    max_size: Tuple[int, int] = (1024, 1024),
    quality: int = 75,
) -> Optional[bytes]:
    """
    Compresses an in-memory image to WebP format:
    - Resizes maintaining aspect ratio if exceeding max_size
    - Converts to RGB (handling RGBA transparency safely for WebP)
    - Exports to WebP at target quality (default 75%)
    - Reduces payload size typically from 5-8MB down to 40-70KB
    - Returns None if image buffer is corrupted or invalid (fail-safe)
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Correct EXIF orientation if present
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            # Proportional resizing if larger than max_size
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # RGB conversion if necessary (e.g. CMYK or palette)
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                pass
            elif img.mode != "RGB":
                img = img.convert("RGB")

            output_io = io.BytesIO()
            img.save(output_io, format="WEBP", quality=quality, optimize=True)
            compressed_bytes = output_io.getvalue()

            orig_len = len(image_bytes)
            comp_len = len(compressed_bytes)
            logger.info(
                f"Image compression complete: {orig_len // 1024} KB -> {comp_len // 1024} KB "
                f"({100 - (comp_len * 100 // max(orig_len, 1))}% space saved)"
            )
            return compressed_bytes

    except Exception as e:
        logger.error(f"WebP compression error (invalid or corrupted file): {e}")
        return None
