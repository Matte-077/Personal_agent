"""
Database access and query module (Supabase & SQLite dual-mode).
"""

from src.db.supabase_client import get_supabase_client
from src.db.queries import (
    save_item,
    search_semantic,
    search_fulltext,
    search_by_ingredients,
    search_automotive,
    get_recent_items,
)

__all__ = [
    "get_supabase_client",
    "save_item",
    "search_semantic",
    "search_fulltext",
    "search_by_ingredients",
    "search_automotive",
    "get_recent_items",
]
