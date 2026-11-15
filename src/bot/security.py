import hashlib
import hmac
import json
import logging
import time
from collections import defaultdict
from functools import wraps
from typing import Callable, Any, Dict, List, Optional
from urllib.parse import parse_qsl
from telegram import Update
from telegram.ext import ContextTypes
from src.config import settings

logger = logging.getLogger(__name__)

# Sliding window rate limiter in memory (user_id -> list of timestamps)
_user_timestamps: Dict[int, List[float]] = defaultdict(list)
MAX_REQUESTS_PER_MINUTE = 15
RATE_LIMIT_WINDOW_SECONDS = 60.0


def check_rate_limit(user_id: int) -> bool:
    """
    Checks whether a user respects the allowed rate limit (max 15 requests/minute).
    Returns True if request is permitted, False if threshold exceeded.
    """
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    valid_timestamps = [t for t in _user_timestamps[user_id] if t > cutoff]

    if len(valid_timestamps) >= MAX_REQUESTS_PER_MINUTE:
        _user_timestamps[user_id] = valid_timestamps
        return False

    valid_timestamps.append(now)
    _user_timestamps[user_id] = valid_timestamps
    return True


def reset_rate_limits() -> None:
    """Resets rate limiter memory (used in unit tests)."""
    _user_timestamps.clear()


def validate_telegram_init_data(init_data: str, bot_token: str) -> Optional[int]:
    """
    Validates cryptographic initData string sent by Telegram WebApp.
    Uses HMAC-SHA256 with key derived from WebAppData to verify that data
    genuinely originates from Telegram and belongs to an authorized user.
    Returns Telegram user_id if valid, otherwise None.
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))
        hash_received = parsed_data.pop("hash", None)
        if not hash_received:
            return None

        # Reconstruct data_check_string (alphabetically sorted keys joined with newline)
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))

        # Compute secret_key = HMAC-SHA256("WebAppData", bot_token)
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if calculated_hash.lower() != hash_received.lower():
            logger.warning("Telegram WebApp HMAC signature invalid.")
            return None

        user_raw = parsed_data.get("user")
        if not user_raw:
            return None

        user_data = json.loads(user_raw)
        user_id = user_data.get("id")
        return int(user_id) if user_id else None
    except Exception as e:
        logger.warning(f"Error validating Telegram initData: {e}")
        return None


def create_web_access_token(user_id: int | str, secret: str) -> str:
    """Generates a signed desktop browser access token valid for 48 hours."""
    exp = int(time.time()) + 48 * 3600
    payload = f"{user_id}:{exp}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    return f"{payload}:{signature}"


def verify_web_access_token(token: str, secret: str) -> Optional[str]:
    """Verifies desktop browser access token. Returns user_id if valid, otherwise None."""
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return None
        user_id, exp_str, sig = parts
        if int(exp_str) < time.time():
            return None
        payload = f"{user_id}:{exp_str}"
        expected_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        if hmac.compare_digest(sig, expected_sig):
            return str(user_id)
        return None
    except Exception:
        return None


def restricted(func: Callable) -> Callable:
    """
    Decorator for python-telegram-bot handlers.
    1. Verifies that the sender user ID is present in ALLOWED_TELEGRAM_USER_IDS.
    2. Enforces sliding window rate limiting (max 15 msg/min).
    If unauthorized or rate limited, stops processing to protect privacy and API quota.
    """
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        user = update.effective_user
        if not user:
            logger.warning("Received update without effective_user. Discarded.")
            return

        # 1. Whitelist Verification
        if not settings.is_user_allowed(user.id):
            logger.warning(
                f"Unauthorized access attempt: user_id={user.id}, username=@{user.username}"
            )
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ Accesso non autorizzato. Questo bot è privato."
                )
            return

        # 2. Rate Limit Verification
        if not check_rate_limit(user.id):
            logger.warning(f"Rate limit exceeded for user_id={user.id}")
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⏳ Troppe richieste ravvicinate. Attendi un momento prima di inviare un nuovo messaggio."
                )
            return

        return await func(update, context, *args, **kwargs)

    return wrapped
