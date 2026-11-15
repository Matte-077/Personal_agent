import logging
from typing import Optional
from supabase import create_client, Client
from src.config import settings

logger = logging.getLogger(__name__)

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Returns a singleton instance of authenticated Supabase client
    using SUPABASE_URL and backend key (Secret Key / service_role).
    """
    global _supabase_client
    if _supabase_client is None:
        url = settings.SUPABASE_URL
        key = settings.supabase_key

        if not url or not key:
            raise ValueError(
                "SUPABASE_URL or SUPABASE_SECRET_KEY / SUPABASE_SERVICE_ROLE_KEY not configured in .env"
            )

        logger.info(f"Initializing Supabase client targeting: {url}")
        _supabase_client = create_client(url, key)

    return _supabase_client
