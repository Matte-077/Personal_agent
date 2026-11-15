import json
import logging
import math
import random
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.db.sqlite_client import get_sqlite_connection
from src.config import settings

logger = logging.getLogger(__name__)


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Converts an sqlite3.Row into a dictionary with deserialized JSON fields."""
    d = dict(row)
    # JSON field deserialization
    if "tags" in d and isinstance(d["tags"], str):
        try:
            d["tags"] = json.loads(d["tags"])
        except Exception:
            d["tags"] = []

    if "metadata" in d and isinstance(d["metadata"], str):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except Exception:
            d["metadata"] = {}

    if "embedding" in d and isinstance(d["embedding"], str):
        try:
            d["embedding"] = json.loads(d["embedding"])
        except Exception:
            d["embedding"] = None

    if "confidence" in d and d["confidence"] is not None:
        try:
            d["confidence"] = float(d["confidence"])
        except Exception:
            pass

    return d


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculates cosine similarity between two N-dimensional vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(vec1, vec2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 <= 0.0 or norm2 <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm1) * math.sqrt(norm2))


def save_item(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Saves an item into the local SQLite database.
    Isolates records by user_id: if user already saved 'source_url', updates existing record (upsert).
    """
    conn = get_sqlite_connection()
    source_url = record.get("source_url")
    user_id = str(record.get("user_id", "default"))
    now_iso = datetime.now(timezone.utc).isoformat()

    item_id = str(record.get("id") or uuid.uuid4())
    status = record.get("status", "active")
    created_at = record.get("created_at") or now_iso
    updated_at = now_iso
    source_type = record.get("source_type", "other")
    raw_text = record.get("raw_text") or ""
    category = record.get("category", "Altro / Varie & Non Classificato")
    subcategory = record.get("subcategory")
    title = record.get("title") or "Untitled"
    summary = record.get("summary") or ""
    confidence = float(record.get("confidence", 1.0))

    tags_json = json.dumps(record.get("tags") or [], ensure_ascii=False)
    metadata_json = json.dumps(record.get("metadata") or {}, ensure_ascii=False)
    embedding_json = json.dumps(record.get("embedding")) if record.get("embedding") else None

    with conn:
        cursor = conn.cursor()
        if source_url:
            cursor.execute(
                "SELECT id FROM items WHERE source_url = ? AND user_id = ? LIMIT 1",
                (source_url, user_id),
            )
            existing = cursor.fetchone()
            if existing:
                existing_id = existing["id"]
                logger.info(f"[SQLite] Updating existing record for {user_id} with URL {source_url} (id: {existing_id})")
                cursor.execute("""
                    UPDATE items SET
                        status = ?,
                        updated_at = ?,
                        source_type = ?,
                        raw_text = ?,
                        category = ?,
                        subcategory = ?,
                        title = ?,
                        summary = ?,
                        tags = ?,
                        metadata = ?,
                        confidence = ?,
                        embedding = ?
                    WHERE id = ?
                """, (
                    status, updated_at, source_type, raw_text, category, subcategory,
                    title, summary, tags_json, metadata_json, confidence, embedding_json,
                    existing_id
                ))
                cursor.execute("SELECT * FROM items WHERE id = ?", (existing_id,))
                return _row_to_dict(cursor.fetchone())

        logger.info(f"[SQLite] Inserting new record: '{title}' in '{category}' for {user_id}")
        cursor.execute("""
            INSERT INTO items (
                id, user_id, status, created_at, updated_at, source_url, source_type,
                raw_text, category, subcategory, title, summary, tags, metadata,
                confidence, embedding
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id, user_id, status, created_at, updated_at, source_url, source_type,
            raw_text, category, subcategory, title, summary, tags_json, metadata_json,
            confidence, embedding_json
        ))
        cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        return _row_to_dict(cursor.fetchone())


def search_semantic(
    embedding: List[float],
    match_count: int = 5,
    match_threshold: Optional[float] = None,
    category: Optional[str] = None,
    user_id: str = "default",
) -> List[Dict[str, Any]]:
    """Ricerca semantica vettoriale calcolando la similarità coseno in memoria su SQLite."""
    if match_threshold is None:
        match_threshold = settings.DEFAULT_MATCH_THRESHOLD

    conn = get_sqlite_connection()
    cursor = conn.cursor()

    sql = "SELECT * FROM items WHERE status = 'active' AND embedding IS NOT NULL"
    params: List[Any] = []

    if user_id != "all":
        sql += " AND user_id = ?"
        params.append(user_id)

    if category:
        sql += " AND category = ?"
        params.append(category)

    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()

    scored_items = []
    for r in rows:
        d = _row_to_dict(r)
        item_emb = d.get("embedding")
        if item_emb and isinstance(item_emb, list):
            sim = _cosine_similarity(embedding, item_emb)
            if sim >= match_threshold:
                d["similarity"] = round(sim, 4)
                scored_items.append(d)

    scored_items.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
    return scored_items[:match_count]


def search_fulltext(
    query_text: str,
    user_id: str = "default",
    limit: int = 5,
    category: Optional[str] = None,
    language: str = "italian",
) -> List[Dict[str, Any]]:
    """Ricerca Full-Text su SQLite tramite FTS5 con fallback su LIKE."""
    clean_query = query_text.strip()
    if not clean_query:
        return []

    conn = get_sqlite_connection()
    cursor = conn.cursor()

    # 1. Prova con FTS5 se disponibile
    try:
        # Pulisce parole per sintassi FTS5
        words = re.findall(r"\w+", clean_query)
        if words:
            fts_match_expr = " OR ".join(f'"{w}"*' for w in words)
            sql = """
                SELECT items.* FROM items
                JOIN items_fts ON items.id = items_fts.id
                WHERE items.status = 'active'
                  AND items_fts MATCH ?
            """
            params: List[Any] = [fts_match_expr]

            if user_id != "all":
                sql += " AND items.user_id = ?"
                params.append(user_id)
            if category:
                sql += " AND items.category = ?"
                params.append(category)

            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)

            cursor.execute(sql, tuple(params))
            results = [_row_to_dict(r) for r in cursor.fetchall()]
            if results:
                return results
    except Exception as e:
        logger.debug(f"[SQLite] FTS5 fallito o non abilitato ({e}), fallback su LIKE")

    # 2. Fallback su LIKE standard
    sql = "SELECT * FROM items WHERE status = 'active'"
    params = []
    if user_id != "all":
        sql += " AND user_id = ?"
        params.append(user_id)
    if category:
        sql += " AND category = ?"
        params.append(category)

    # Tokenizza le parole della query
    tokens = [t for t in clean_query.split() if len(t) > 1]
    if tokens:
        like_clauses = []
        for t in tokens[:4]:
            like_clauses.append("(title LIKE ? OR summary LIKE ? OR tags LIKE ?)")
            params.extend([f"%{t}%", f"%{t}%", f"%{t}%"])
        sql += " AND (" + " OR ".join(like_clauses) + ")"

    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, tuple(params))
    return [_row_to_dict(r) for r in cursor.fetchall()]


def compute_rrf(
    rank_lists: List[List[Dict[str, Any]]],
    k: int = 60,
    weights: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """Calcola il Reciprocal Rank Fusion (RRF) combinando graduatorie."""
    if not rank_lists:
        return []

    if weights is None:
        weights = [1.0] * len(rank_lists)
    elif len(weights) != len(rank_lists):
        weights = [1.0] * len(rank_lists)

    scores: Dict[str, float] = {}
    items_by_id: Dict[str, Dict[str, Any]] = {}
    ranks_by_id: Dict[str, Dict[str, int]] = {}

    for list_idx, r_list in enumerate(rank_lists):
        w = weights[list_idx]
        for rank_pos, item in enumerate(r_list, start=1):
            item_id = str(item.get("id"))
            if not item_id:
                continue

            items_by_id[item_id] = item
            if item_id not in scores:
                scores[item_id] = 0.0
                ranks_by_id[item_id] = {}

            scores[item_id] += w / (k + rank_pos)
            ranks_by_id[item_id][f"rank_list_{list_idx + 1}"] = rank_pos

    sorted_ids = sorted(scores.keys(), key=lambda i: scores[i], reverse=True)
    fused_results = []
    for item_id in sorted_ids:
        item_copy = dict(items_by_id[item_id])
        item_copy["rrf_score"] = round(scores[item_id], 6)
        item_copy["rrf_ranks"] = ranks_by_id[item_id]
        fused_results.append(item_copy)

    return fused_results


def search_hybrid_rrf(
    query_text: str,
    query_embedding: Optional[List[float]] = None,
    user_id: str = "default",
    limit: int = 5,
    category: Optional[str] = None,
    k: int = 60,
) -> List[Dict[str, Any]]:
    """Ricerca ibrida avanzata RRF per SQLite."""
    rank_lists: List[List[Dict[str, Any]]] = []

    if query_embedding:
        try:
            semantic_matches = search_semantic(
                embedding=query_embedding,
                match_count=limit * 2,
                category=category,
                user_id=user_id,
            )
            if semantic_matches:
                rank_lists.append(semantic_matches)
        except Exception as e:
            logger.warning(f"[SQLite] Errore semantico per RRF: {e}")

    clean_text = re.sub(r"[^\w\s]", " ", query_text).strip()
    if clean_text:
        try:
            fts_matches = search_fulltext(
                query_text=clean_text,
                user_id=user_id,
                limit=limit * 2,
                category=category,
            )
            if fts_matches:
                rank_lists.append(fts_matches)
        except Exception as e:
            logger.warning(f"[SQLite] Errore FTS per RRF: {e}")

    if not rank_lists:
        return []
    if len(rank_lists) == 1:
        return rank_lists[0][:limit]

    fused = compute_rrf(rank_lists, k=k)
    return fused[:limit]


def search_by_ingredients(
    ingredients: List[str],
    user_id: str = "default",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Cerca ricette contenenti uno o più ingredienti nel JSON metadata di SQLite."""
    clean_ingredients = [ing.strip().lower() for ing in ingredients if ing.strip()]
    if not clean_ingredients:
        return []

    conn = get_sqlite_connection()
    cursor = conn.cursor()

    sql = "SELECT * FROM items WHERE category = 'Cucina & Alimentazione' AND status = 'active'"
    params: List[Any] = []
    if user_id != "all":
        sql += " AND user_id = ?"
        params.append(user_id)

    sql += " ORDER BY created_at DESC"
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()

    matching_all = []
    matching_any = []

    for r in rows:
        d = _row_to_dict(r)
        item_ings = d.get("metadata", {}).get("ingredienti_principali") or []
        item_ings_lower = [str(x).strip().lower() for x in item_ings]

        # Verifica contenimento
        has_all = all(any(req in ing for ing in item_ings_lower) for req in clean_ingredients)
        has_any = any(any(req in ing for ing in item_ings_lower) for req in clean_ingredients)

        if has_all:
            matching_all.append(d)
        elif has_any:
            matching_any.append(d)

    if matching_all:
        return matching_all[:limit]
    return matching_any[:limit]


def search_automotive(
    max_price: Optional[int] = None,
    min_price: Optional[int] = None,
    laser_lights: bool = False,
    g21_only: bool = False,
    user_id: str = "default",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Filtra annunci auto con confronto numerico su prezzo e optional in SQLite."""
    conn = get_sqlite_connection()
    cursor = conn.cursor()

    sql = "SELECT * FROM items WHERE category = 'Automotive & Annunci Auto' AND status = 'active'"
    params: List[Any] = []
    if user_id != "all":
        sql += " AND user_id = ?"
        params.append(user_id)

    sql += " ORDER BY created_at DESC"
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()

    filtered = []
    for r in rows:
        item = _row_to_dict(r)
        meta = item.get("metadata") or {}

        # Filtro G21
        if g21_only:
            carrozz = str(meta.get("carrozzeria_generazione") or "") + str(meta.get("modello") or "")
            if "g21" not in carrozz.lower() and "touring" not in carrozz.lower():
                continue

        # Filtro Laser
        if laser_lights:
            opts = meta.get("optional_chiave") or []
            if isinstance(opts, list):
                has_laser = any("laser" in str(o).lower() for o in opts)
            else:
                has_laser = "laser" in str(opts).lower()
            if not has_laser:
                continue

        # Filtri prezzo numerico
        price = meta.get("prezzo_eur")
        if price is not None:
            try:
                price_num = float(price)
                if max_price is not None and price_num > max_price:
                    continue
                if min_price is not None and price_num < min_price:
                    continue
            except (ValueError, TypeError):
                pass
        elif max_price is not None or min_price is not None:
            continue

        filtered.append(item)
        if len(filtered) >= limit:
            break

    return filtered


def get_recent_items(
    user_id: str = "default",
    limit: int = 5,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Restituisce gli ultimi elementi attivi salvati in SQLite."""
    conn = get_sqlite_connection()
    cursor = conn.cursor()

    sql = "SELECT * FROM items WHERE status = 'active'"
    params: List[Any] = []
    if user_id != "all":
        sql += " AND user_id = ?"
        params.append(user_id)
    if category:
        sql += " AND category = ?"
        params.append(category)

    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, tuple(params))
    return [_row_to_dict(r) for r in cursor.fetchall()]


def soft_delete_item(item_id: str, user_id: str = "default") -> bool:
    """Soft delete di un elemento in SQLite (status='deleted')."""
    conn = get_sqlite_connection()
    with conn:
        cursor = conn.cursor()
        sql = "UPDATE items SET status = 'deleted', updated_at = ? WHERE id = ?"
        params: List[Any] = [datetime.now(timezone.utc).isoformat(), item_id]
        if user_id != "all":
            sql += " AND user_id = ?"
            params.append(user_id)

        cursor.execute(sql, tuple(params))
        return cursor.rowcount > 0


def get_item_by_id(item_id: str, user_id: str = "default") -> Optional[Dict[str, Any]]:
    """Recupera un singolo elemento per ID in SQLite."""
    conn = get_sqlite_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM items WHERE id = ?"
    params: List[Any] = [item_id]
    if user_id != "all":
        sql += " AND user_id = ?"
        params.append(user_id)
    sql += " LIMIT 1"

    cursor.execute(sql, tuple(params))
    row = cursor.fetchone()
    return _row_to_dict(row) if row else None


def find_active_items_by_keyword(
    query_text: str,
    user_id: str = "default",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Cerca elementi attivi per keyword su titolo o FTS per eliminazione o consultazione."""
    clean_q = query_text.strip()
    if not clean_q:
        return []

    conn = get_sqlite_connection()
    cursor = conn.cursor()

    sql = "SELECT id, title, category, created_at, source_url FROM items WHERE status = 'active' AND title LIKE ?"
    params: List[Any] = [f"%{clean_q}%"]
    if user_id != "all":
        sql += " AND user_id = ?"
        params.append(user_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    if rows:
        return [_row_to_dict(r) for r in rows]

    return search_fulltext(clean_q, user_id=user_id, limit=limit)


def get_recent_receipts_or_pantry(
    user_id: str = "default",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Recupera gli scontrini recenti o le schede spesa/dispensa dell'utente in SQLite."""
    conn = get_sqlite_connection()
    cursor = conn.cursor()

    sql = """
        SELECT * FROM items
        WHERE status = 'active'
          AND (source_type = 'receipt' OR (category = 'Cucina & Alimentazione' AND subcategory LIKE '%scontrino%'))
    """
    params: List[Any] = []
    if user_id != "all":
        sql += " AND user_id = ?"
        params.append(user_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, tuple(params))
    return [_row_to_dict(r) for r in cursor.fetchall()]


def get_random_educational_item(user_id: str = "default") -> Optional[Dict[str, Any]]:
    """Seleziona un elemento attivo salvato a scopo di ripasso / micro-learning (/pillola) in SQLite."""
    conn = get_sqlite_connection()
    cursor = conn.cursor()

    categories = [
        "AI, Tech & Software",
        "Produttività, Finanza Personale & Business",
        "Life Hacks, Casa & Fai da Te",
        "Notizie, Attualità & Economia",
        "Cucina & Alimentazione",
        "Fitness, Sport & Salute",
    ]
    placeholders = ",".join("?" for _ in categories)
    sql = f"SELECT * FROM items WHERE status = 'active' AND category IN ({placeholders})"
    params: List[Any] = list(categories)

    if user_id != "all":
        sql += " AND user_id = ?"
        params.append(user_id)

    sql += " ORDER BY created_at DESC LIMIT 30"
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    items = [_row_to_dict(r) for r in rows]

    if not items:
        fallback_sql = "SELECT * FROM items WHERE status = 'active'"
        fb_params: List[Any] = []
        if user_id != "all":
            fallback_sql += " AND user_id = ?"
            fb_params.append(user_id)
        fallback_sql += " ORDER BY created_at DESC LIMIT 20"
        cursor.execute(fallback_sql, tuple(fb_params))
        items = [_row_to_dict(r) for r in cursor.fetchall()]

    if not items:
        return None

    return random.choice(items)

