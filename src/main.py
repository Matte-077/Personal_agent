import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from src.config import settings
from src.bot.handlers import (
    handle_text_message,
    handle_media_message,
    handle_start_help,
    handle_unsupported_media,
    handle_elimina_command,
    handle_delete_callback,
    handle_pillola_command,
    handle_dashboard_command,
)
from src.bot.security import validate_telegram_init_data, verify_web_access_token, create_web_access_token
from src.db.queries import get_recent_items, soft_delete_item

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Global Telegram Bot application instance
bot_app: Application | None = None


def build_bot_app() -> Application | None:
    """Creates and configures python-telegram-bot application."""
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not configured. Telegram bot not initialized.")
        return None

    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Register message and command handlers
    app.add_handler(CommandHandler(["start", "help"], handle_start_help))
    app.add_handler(CommandHandler(["elimina", "cancella"], handle_elimina_command))
    app.add_handler(CommandHandler(["pillola", "impara", "ripasso"], handle_pillola_command))
    app.add_handler(CommandHandler(["dashboard", "app"], handle_dashboard_command))
    app.add_handler(CallbackQueryHandler(handle_delete_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(
        MessageHandler(
            filters.VOICE | filters.AUDIO | filters.VIDEO | filters.PHOTO,
            handle_media_message,
        )
    )
    # Unsupported formats (stickers, generic documents, location, contacts)
    app.add_handler(
        MessageHandler(
            filters.Document.ALL | filters.Sticker.ALL | filters.LOCATION | filters.CONTACT,
            handle_unsupported_media,
        )
    )

    # Global error handler with user feedback
    async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(f"Unhandled error in Telegram bot: {context.error}", exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ Si è verificato un errore imprevisto durante l'elaborazione della tua richiesta. Riprova più tardi."
                )
            except Exception as e:
                logger.error(f"Could not deliver error notification to user: {e}")

    app.add_error_handler(global_error_handler)
    return app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan manager:
    Initializes Telegram bot in Polling (local) or Webhook (cloud) mode.
    """
    global bot_app
    bot_app = build_bot_app()

    if bot_app:
        await bot_app.initialize()
        await bot_app.start()

        if settings.BOT_MODE == "polling":
            # LOCAL MODE / POLLING (behind router/firewall without open ports)
            logger.info("Polling mode active: removing webhook and starting local ingestion...")
            pending_count = 0
            try:
                info = await bot_app.bot.get_webhook_info()
                pending_count = info.pending_update_count or 0
                logger.info(f"Backlog messages in Telegram queue to process: {pending_count}")
                await bot_app.bot.delete_webhook(drop_pending_updates=False)
            except Exception as e:
                logger.warning(f"Error removing webhook prior to polling: {e}")

            if bot_app.updater:
                await bot_app.updater.start_polling(
                    drop_pending_updates=False,
                    allowed_updates=["message", "callback_query"],
                )
                logger.info("Telegram polling started successfully. Local reception active.")

            if settings.LOCAL_NOTIFY_ON_BOOT and settings.allowed_user_ids:
                first_user_id = next(iter(settings.allowed_user_ids))
                token = create_web_access_token(first_user_id, settings.TELEGRAM_BOT_TOKEN or "secret")
                local_url = f"http://localhost:{settings.PORT}/app?token={token}"
                msg = (
                    "🖥️ <b>Agente Personale Locale Online!</b>\n\n"
                    f"📦 <b>Messaggi arretrati in coda:</b> {pending_count}\n"
                    f"🌐 <b>Dashboard:</b> <a href=\"{local_url}\">Apri Dashboard Locale</a>\n\n"
                    "<i>Tutti i comandi e l'archivio sono pronti all'uso.</i>"
                )
                try:
                    await bot_app.bot.send_message(
                        chat_id=first_user_id,
                        text=msg,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                except Exception as notify_err:
                    logger.debug(f"Local boot notification not sent: {notify_err}")

        else:
            # CLOUD MODE / WEBHOOK (Render)
            if settings.WEBHOOK_URL:
                webhook_target = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook"
                logger.info(f"Configuring Telegram Webhook on: {webhook_target}")
                await bot_app.bot.set_webhook(
                    url=webhook_target,
                    secret_token=settings.TELEGRAM_WEBHOOK_SECRET or None,
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=False,
                )
            else:
                logger.info("No WEBHOOK_URL configured. Set WEBHOOK_URL in .env or set BOT_MODE=polling for local execution.")

    yield

    # Shutdown
    if bot_app:
        logger.info("Stopping Telegram bot...")
        if bot_app.updater and getattr(bot_app.updater, "running", False):
            await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()


app = FastAPI(
    title="Personal AI Assistant - Second Brain",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount local storage directory for uploaded car photos and media
local_storage_path = Path(settings.LOCAL_STORAGE_DIR)
if not local_storage_path.is_absolute():
    local_storage_path = Path.cwd() / local_storage_path
local_storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(local_storage_path)), name="storage")


@app.api_route("/", methods=["GET", "HEAD"], tags=["Health"])
@app.api_route("/healthz", methods=["GET", "HEAD"], tags=["Health"])
@app.api_route("/health", methods=["GET", "HEAD"], tags=["Health"])
async def health_check():
    """
    Lightweight keep-alive endpoint to prevent Render service cold-starts.
    Supports GET and HEAD methods (default for UptimeRobot) across /, /healthz and /health.
    """
    return {
        "status": "healthy",
        "service": "agente-personale",
        "environment": settings.ENVIRONMENT,
        "utc_time": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/webhook", tags=["Telegram"])
async def telegram_webhook(request: Request):
    """
    Receives incoming HTTPS POST updates sent by Telegram.
    """
    # 1. Verify webhook secret token (perimeter security guard)
    if settings.TELEGRAM_WEBHOOK_SECRET:
        secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret_header != settings.TELEGRAM_WEBHOOK_SECRET:
            logger.warning("Webhook rejected: invalid secret token.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Secret token non valido.",
            )

    # 2. Safely parse JSON payload
    try:
        data = await request.json()
    except Exception as e:
        logger.warning(f"Webhook received invalid or empty JSON payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload JSON non valido.",
        )

    # 3. Verify Telegram bot worker availability
    if not bot_app:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot not configured.",
        )

    update = Update.de_json(data, bot_app.bot)
    if update:
        await bot_app.process_update(update)

    return JSONResponse(content={"status": "ok"})


def get_current_dashboard_user(request: Request) -> str:
    """
    Authenticates user for dashboard API requests:
    1. Via X-Telegram-Init-Data header (if opened inside Telegram WebApp / Mini App)
    2. Via signed desktop access token (in X-Web-Access-Token header or ?token= query parameter)
    Also verifies that the user ID is present in ALLOWED_TELEGRAM_USER_IDS.
    """
    # 1. Telegram WebApp initData
    init_data = request.headers.get("X-Telegram-Init-Data")
    if init_data and settings.TELEGRAM_BOT_TOKEN:
        uid = validate_telegram_init_data(init_data, settings.TELEGRAM_BOT_TOKEN)
        if uid is not None and settings.is_user_allowed(uid):
            return str(uid)

    # 2. Desktop Token (Header or Query Param)
    token = request.headers.get("X-Web-Access-Token") or request.query_params.get("token")
    if token and settings.TELEGRAM_BOT_TOKEN:
        uid_str = verify_web_access_token(token, settings.TELEGRAM_BOT_TOKEN)
        if uid_str:
            try:
                uid_int = int(uid_str)
                if settings.is_user_allowed(uid_int):
                    return str(uid_int)
            except ValueError:
                pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Non autorizzato. Apri la dashboard tramite Telegram con il comando /dashboard.",
    )


@app.get("/app", response_class=HTMLResponse, tags=["Dashboard"])
@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
async def serve_dashboard():
    """Serves the Single Page App / Telegram Mini App Dashboard."""
    html_path = Path(__file__).parent / "static" / "dashboard.html"
    if not html_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File della dashboard non trovato.",
        )
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/dashboard/items", tags=["Dashboard"])
async def get_dashboard_items(request: Request, category: Optional[str] = None):
    """Returns active user cards for dashboard."""
    user_id = get_current_dashboard_user(request)
    items = get_recent_items(user_id=user_id, limit=100, category=category)
    return JSONResponse(content=items)


@app.post("/api/dashboard/delete/{item_id}", tags=["Dashboard"])
@app.delete("/api/dashboard/delete/{item_id}", tags=["Dashboard"])
async def delete_dashboard_item(item_id: str, request: Request):
    """Soft-deletes a card from the dashboard."""
    user_id = get_current_dashboard_user(request)
    success = soft_delete_item(item_id=item_id, user_id=user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheda non trovata o già eliminata.",
        )
    return JSONResponse(content={"status": "deleted", "id": item_id})

