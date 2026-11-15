import argparse
import logging
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import uvicorn
from src.config import settings
from src.bot.security import create_web_access_token

logger = logging.getLogger("local_runner")


def parse_args():
    parser = argparse.ArgumentParser(description="Personal AI Assistant Local Runner (Second Brain)")
    parser.add_argument("--port", type=int, default=settings.PORT, help="HTTP port for the local server (default: 8000)")
    parser.add_argument("--db", choices=["sqlite", "supabase"], default=settings.DB_PROVIDER, help="Database provider (sqlite or supabase)")
    parser.add_argument("--ai", choices=["gemini", "ollama"], default=settings.AI_PROVIDER, help="AI provider (gemini or ollama)")
    parser.add_argument("--open-browser", action="store_true", default=settings.AUTO_OPEN_BROWSER, help="Automatically open Dashboard in default browser on launch")
    parser.add_argument("--no-notify", action="store_true", help="Do not send Telegram notification on launch")
    return parser.parse_args()


def print_banner(port: int, db_mode: str, ai_mode: str, dashboard_url: str):
    banner = f"""
=============================================================================
  ⚡ PERSONAL AI ASSISTANT — SECOND BRAIN (LOCAL MODE)
=============================================================================
  [STATUS]:         ONLINE & READY
  [BOT MODE]:       Long-Polling (No open ports needed, firewall/NAT-proof)
  [CATCH-UP]:       Active (Processes any backlog messages sent while offline)
  [DATABASE]:       {db_mode.upper()} {'(data/agente.db + FTS5)' if db_mode == 'sqlite' else '(Supabase Cloud PostgreSQL + pgvector)'}
  [AI ENGINE]:      {ai_mode.upper()} {'(Ollama Local 100% Offline)' if ai_mode == 'ollama' else '(Google Gemini Flash Lite 3.1)'}
  [HTTP PORT]:      {port}
  [DASHBOARD]:      {dashboard_url}
=============================================================================
  Quick Tips:
  - Share links, voice memos, or receipt photos with your Telegram bot.
  - Open the dashboard in your browser to view cards and compare items.
  - Press CTRL+C in this terminal window to stop the service cleanly.
=============================================================================
"""
    print(banner)


def open_browser_delayed(url: str, delay: float = 1.8):
    """Opens the dashboard in default browser after a short delay to await uvicorn startup."""
    def _open():
        time.sleep(delay)
        try:
            logger.info(f"Opening Dashboard in browser: {url}")
            webbrowser.open(url)
        except Exception as e:
            logger.warning(f"Could not automatically open browser: {e}")

    thread = threading.Thread(target=_open, daemon=True)
    thread.start()


def main():
    args = parse_args()

    # 1. Enforce local execution settings
    settings.BOT_MODE = "polling"
    settings.DB_PROVIDER = args.db
    settings.AI_PROVIDER = args.ai
    settings.PORT = args.port
    if args.no_notify:
        settings.LOCAL_NOTIFY_ON_BOOT = False

    # 2. Generate authenticated access token for desktop browser
    first_user_id = next(iter(settings.allowed_user_ids)) if settings.allowed_user_ids else "default"
    token = create_web_access_token(first_user_id, settings.TELEGRAM_BOT_TOKEN or "local_secret")
    dashboard_url = f"http://localhost:{args.port}/app?token={token}"

    # 3. Print information banner
    print_banner(port=args.port, db_mode=args.db, ai_mode=args.ai, dashboard_url=dashboard_url)

    # 4. Optional browser launch
    if args.open_browser:
        open_browser_delayed(dashboard_url)

    # 5. Start FastAPI server (lifespan initiates Telegram long-polling)
    try:
        from src.main import app
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=args.port,
            log_level="info",
            access_log=False,
        )
    except KeyboardInterrupt:
        print("\n🛑 Local Personal AI Assistant stopped cleanly. Goodbye!")


if __name__ == "__main__":
    main()

