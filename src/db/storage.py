import logging
import uuid
from pathlib import Path
from typing import Optional
from src.config import settings

logger = logging.getLogger(__name__)

BUCKET_NAME = "car-photos"
_bucket_verified: bool = False


def ensure_storage_bucket():
    """Verifies once that the vehicle photo bucket exists in Supabase Storage."""
    global _bucket_verified
    if _bucket_verified:
        return

    try:
        from src.db.supabase_client import get_supabase_client
        sb = get_supabase_client()
        existing = [b.name for b in sb.storage.list_buckets()]
        if BUCKET_NAME not in existing:
            sb.storage.create_bucket(BUCKET_NAME, options={"public": True})
            logger.info(f"Storage bucket '{BUCKET_NAME}' created successfully.")
        _bucket_verified = True
    except Exception as e:
        logger.warning(f"Storage bucket check '{BUCKET_NAME}': {e}")


def upload_car_photo(
    photo_bytes: bytes,
    filename: Optional[str] = None,
    user_id: str = "default",
    content_type: str = "image/webp",
) -> Optional[str]:
    """
    Uploads compressed WebP image bytes:
    - If DB_PROVIDER == 'sqlite': saves to local disk in LOCAL_STORAGE_DIR/uploads/{user_id}/{filename}
      and returns relative URL '/storage/uploads/{user_id}/{filename}' served by FastAPI.
    - If DB_PROVIDER == 'supabase': uploads to Supabase Storage bucket and returns public URL.
    """
    safe_user_id = "".join(c for c in user_id if c.isalnum() or c in ("-", "_")) or "default"
    if not filename:
        filename = f"car_{uuid.uuid4().hex[:12]}.webp"
    elif not filename.endswith(".webp"):
        filename = f"{filename}.webp"

    # 1. Local Storage Mode (SQLite / Offline / Zero-Cloud)
    if settings.DB_PROVIDER == "sqlite" or not settings.SUPABASE_URL:
        try:
            local_dir = Path(settings.LOCAL_STORAGE_DIR)
            if not local_dir.is_absolute():
                local_dir = Path.cwd() / local_dir

            target_dir = local_dir / "uploads" / safe_user_id
            target_dir.mkdir(parents=True, exist_ok=True)

            target_file = target_dir / filename
            target_file.write_bytes(photo_bytes)

            local_url = f"/storage/uploads/{safe_user_id}/{filename}"
            logger.info(f"[Local Storage] Photo saved to disk: {target_file} -> {local_url}")
            return local_url
        except Exception as e:
            logger.error(f"Error saving photo locally: {e}", exc_info=True)
            return None

    # 2. Supabase Storage Cloud Mode
    try:
        from src.db.supabase_client import get_supabase_client
        sb = get_supabase_client()
        ensure_storage_bucket()

        path = f"uploads/{safe_user_id}/{filename}"

        sb.storage.from_(BUCKET_NAME).upload(
            path=path,
            file=photo_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )

        public_url = sb.storage.from_(BUCKET_NAME).get_public_url(path)
        logger.info(f"Photo uploaded to Supabase Storage for user {safe_user_id}: {public_url}")
        return public_url

    except Exception as e:
        logger.error(f"Error uploading photo to Supabase Storage: {e}", exc_info=True)
        return None
