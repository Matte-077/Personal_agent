import json
import logging
import re
from typing import Dict, Any, List, Optional
from src.db.supabase_client import get_supabase_client
from src.config import settings
import src.db.sqlite_queries as sqlite_q

logger = logging.getLogger(__name__)


def save_item(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Saves an item into Supabase 'items' table (or SQLite if DB_PROVIDER='sqlite').
    Isolates records by user_id: if user already saved 'source_url', updates existing record (upsert).
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.save_item(record)

    client = get_supabase_client()
    source_url = record.get("source_url")
    user_id = record.get("user_id", "default")

    try:
        if source_url:
            # Check for existing record isolated by user_id
            existing = (
                client.table("items")
                .select("id")
                .eq("source_url", source_url)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if existing.data:
                existing_id = existing.data[0]["id"]
                logger.info(f"Updating existing record for user {user_id} with URL: {source_url} (id: {existing_id})")
                res = (
                    client.table("items")
                    .update(record)
                    .eq("id", existing_id)
                    .execute()
                )
                return res.data[0] if res.data else record

        # Insert new record
        logger.info(f"Inserting new record: '{record.get('title')}' in category '{record.get('category')}' for user {user_id}")
        res = client.table("items").insert(record).execute()
        return res.data[0] if res.data else record
    except Exception as e:
        logger.error(f"Error during save to Supabase: {e}")
        raise


def search_semantic(
    embedding: List[float],
    match_count: int = 5,
    match_threshold: Optional[float] = None,
    category: Optional[str] = None,
    user_id: str = "default",
) -> List[Dict[str, Any]]:
    """
    Ricerca vettoriale basata su similarità coseno tramite la funzione RPC 'match_items'.
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.search_semantic(
            embedding=embedding,
            match_count=match_count,
            match_threshold=match_threshold,
            category=category,
            user_id=user_id,
        )

    if match_threshold is None:
        match_threshold = settings.DEFAULT_MATCH_THRESHOLD

    client = get_supabase_client()
    try:
        params = {
            "query_embedding": embedding,
            "match_threshold": match_threshold,
            "match_count": match_count,
            "filter_user_id": user_id,
            "filter_category": category,
        }
        res = client.rpc("match_items", params).execute()
        return res.data or []
    except Exception as e:
        logger.warning(f"Chiamata RPC match_items fallita: {e}")
        return []


def search_fulltext(
    query_text: str,
    user_id: str = "default",
    limit: int = 5,
    category: Optional[str] = None,
    language: str = "italian",
) -> List[Dict[str, Any]]:
    """
    Ricerca Full-Text su search_tsv con supporto bilingue (italiano o inglese).
    Se la lingua specificata non restituisce risultati o fallisce, prova con fallback incrociato.
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.search_fulltext(
            query_text=query_text,
            user_id=user_id,
            limit=limit,
            category=category,
            language=language,
        )

    client = get_supabase_client()
    clean_query = query_text.strip()
    if not clean_query:
        return []

    try:
        query = (
            client.table("items")
            .select("*")
            .eq("status", "active")
            .text_search("search_tsv", clean_query, options={"config": language})
        )
        if user_id != "all":
            query = query.eq("user_id", user_id)
        if category:
            query = query.eq("category", category)

        res = query.limit(limit).execute()
        if res.data:
            return res.data

        # Fallback sull'altra lingua se non trova risultati
        fallback_lang = "english" if language == "italian" else "italian"
        query_fb = (
            client.table("items")
            .select("*")
            .eq("status", "active")
            .text_search("search_tsv", clean_query, options={"config": fallback_lang})
        )
        if user_id != "all":
            query_fb = query_fb.eq("user_id", user_id)
        if category:
            query_fb = query_fb.eq("category", category)

        res_fb = query_fb.limit(limit).execute()
        return res_fb.data or []
    except Exception as e:
        logger.warning(f"Ricerca Full-Text ({language}) fallita: {e}")
        return []


def compute_rrf(
    rank_lists: List[List[Dict[str, Any]]],
    k: int = 60,
    weights: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """
    Fonde più graduatorie (es. vettoriale semantica e lessicale Full-Text)
    usando l'algoritmo Reciprocal Rank Fusion (RRF).
    
    RRF(d) = sum_i( weight_i / (k + rank_i(d)) )
    """
    if weights is None:
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
    """
    Ricerca Ibrida avanzata tramite Reciprocal Rank Fusion (RRF):
    Combina la ricerca semantica pgvector con la ricerca testuale bilingue (italiano + inglese).
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.search_hybrid_rrf(
            query_text=query_text,
            query_embedding=query_embedding,
            user_id=user_id,
            limit=limit,
            category=category,
            k=k,
        )

    rank_lists: List[List[Dict[str, Any]]] = []

    # 1. Graduatoria semantica vettoriale (pgvector)
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
            logger.warning(f"Errore ricerca semantica per RRF: {e}")

    # 2. Graduatoria Full-Text Search (Bilingue)
    clean_text = re.sub(r"[^\w\s]", " ", query_text).strip()
    if clean_text:
        try:
            fts_matches = search_fulltext(
                query_text=clean_text,
                user_id=user_id,
                limit=limit * 2,
                category=category,
                language="italian",
            )
            if fts_matches:
                rank_lists.append(fts_matches)
        except Exception as e:
            logger.warning(f"Errore ricerca FTS per RRF: {e}")

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
    """
    Cerca ricette contenenti uno o più ingredienti interrogando nativamente Supabase con JSONB containment.
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.search_by_ingredients(
            ingredients=ingredients,
            user_id=user_id,
            limit=limit,
        )

    client = get_supabase_client()
    clean_ingredients = [ing.strip().lower() for ing in ingredients if ing.strip()]
    if not clean_ingredients:
        return []

    try:
        query = (
            client.table("items")
            .select("*")
            .eq("category", "Cucina & Alimentazione")
            .eq("status", "active")
        )
        if user_id != "all":
            query = query.eq("user_id", user_id)

        # Query nativa JSONB containment su Postgres
        query = query.contains("metadata->ingredienti_principali", json.dumps(clean_ingredients))
        res = query.order("created_at", desc=True).limit(limit).execute()
        if res.data:
            return res.data

        # Fallback se non trova tutti gli ingredienti insieme: cerca con il primo ingrediente principale
        if len(clean_ingredients) > 1:
            fallback_query = (
                client.table("items")
                .select("*")
                .eq("category", "Cucina & Alimentazione")
                .eq("status", "active")
            )
            if user_id != "all":
                fallback_query = fallback_query.eq("user_id", user_id)
            fallback_query = fallback_query.contains("metadata->ingredienti_principali", json.dumps([clean_ingredients[0]]))
            res_fallback = fallback_query.order("created_at", desc=True).limit(limit).execute()
            return res_fallback.data or []

        return []
    except Exception as e:
        logger.error(f"Errore ricerca nativa ingredienti: {e}")
        return []


def search_automotive(
    max_price: Optional[int] = None,
    min_price: Optional[int] = None,
    laser_lights: bool = False,
    g21_only: bool = False,
    user_id: str = "default",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Filtra annunci auto con cast numerico nativo tramite RPC 'search_cars' (migrazione 004).
    Include fallback robusto con confronto numerico Python nel caso la RPC non sia ancora applicata.
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.search_automotive(
            max_price=max_price,
            min_price=min_price,
            laser_lights=laser_lights,
            g21_only=g21_only,
            user_id=user_id,
            limit=limit,
        )

    client = get_supabase_client()
    try:
        rpc_params = {
            "filter_user_id": user_id,
            "max_price": max_price,
            "min_price": min_price,
            "g21_only": g21_only,
            "laser_lights": laser_lights,
            "match_limit": limit,
        }
        res = client.rpc("search_cars", rpc_params).execute()
        return res.data or []
    except Exception as e:
        logger.warning(f"RPC search_cars non disponibile o fallita ({e}), fallback su query Supabase")
        try:
            query = (
                client.table("items")
                .select("*")
                .eq("category", "Automotive & Annunci Auto")
                .eq("status", "active")
            )
            if user_id != "all":
                query = query.eq("user_id", user_id)
            if g21_only:
                query = query.ilike("metadata->>carrozzeria_generazione", "%g21%")
            if laser_lights:
                query = query.ilike("metadata->>optional_chiave", "%laser%")

            res = query.order("created_at", desc=True).limit(limit * 2).execute()
            data = res.data or []
            # Filtro numerico in-memory affidabile di fallback
            filtered = []
            for item in data:
                price = item.get("metadata", {}).get("prezzo_eur")
                if price is not None:
                    try:
                        price_num = float(price)
                        if max_price is not None and price_num > max_price:
                            continue
                        if min_price is not None and price_num < min_price:
                            continue
                    except (ValueError, TypeError):
                        pass
                filtered.append(item)
            return filtered[:limit]
        except Exception as e2:
            logger.error(f"Errore ricerca auto fallback su Supabase: {e2}")
            return []


def get_recent_items(
    user_id: str = "default",
    limit: int = 5,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Restituisce gli ultimi elementi salvati.
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.get_recent_items(user_id=user_id, limit=limit, category=category)

    client = get_supabase_client()
    try:
        query = client.table("items").select("*").eq("status", "active")
        if user_id != "all":
            query = query.eq("user_id", user_id)
        if category:
            query = query.eq("category", category)

        res = query.order("created_at", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Errore recupero elementi recenti: {e}")
        return []


def soft_delete_item(item_id: str, user_id: str = "default") -> bool:
    """
    Esegue il soft-delete di un elemento impostando status='deleted'.
    Isolato per id e user_id (tranne se user_id='all').
    Ritorna True se l'operazione ha aggiornato con successo almeno una riga.
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.soft_delete_item(item_id=item_id, user_id=user_id)

    client = get_supabase_client()
    try:
        query = client.table("items").update({"status": "deleted"}).eq("id", item_id)
        if user_id != "all":
            query = query.eq("user_id", user_id)
        res = query.execute()
        return bool(res.data and len(res.data) > 0)
    except Exception as e:
        logger.error(f"Errore soft-delete item {item_id}: {e}")
        return False


def get_item_by_id(item_id: str, user_id: str = "default") -> Optional[Dict[str, Any]]:
    """
    Recupera un singolo elemento per id e user_id.
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.get_item_by_id(item_id=item_id, user_id=user_id)

    client = get_supabase_client()
    try:
        query = client.table("items").select("*").eq("id", item_id)
        if user_id != "all":
            query = query.eq("user_id", user_id)
        res = query.limit(1).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"Errore recupero item {item_id}: {e}")
        return None


def find_active_items_by_keyword(
    query_text: str,
    user_id: str = "default",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Cerca elementi attivi tramite keyword su titolo o FTS per eliminazione o consultazione.
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.find_active_items_by_keyword(query_text=query_text, user_id=user_id, limit=limit)

    clean_q = query_text.strip()
    if not clean_q:
        return []
    client = get_supabase_client()
    try:
        # 1. Ricerca rapida ILIKE su titolo
        query = (
            client.table("items")
            .select("id, title, category, created_at, source_url")
            .eq("status", "active")
            .ilike("title", f"%{clean_q}%")
        )
        if user_id != "all":
            query = query.eq("user_id", user_id)
        res = query.order("created_at", desc=True).limit(limit).execute()
        if res.data:
            return res.data

        # 2. Fallback su Full-Text search se ILIKE sul titolo non trova nulla
        return search_fulltext(clean_q, user_id=user_id, limit=limit)
    except Exception as e:
        logger.warning(f"Errore ricerca attiva per keyword '{query_text}': {e}")
        return []


def get_recent_receipts_or_pantry(
    user_id: str = "default",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Recupera gli scontrini recenti o le schede spesa/dispensa dell'utente.
    Restituisce elementi attivi con source_type='receipt' oppure
    in categoria 'Cucina & Alimentazione' con sottocategoria 'Scontrino Spesa / Dispensa' o campo supermercato.
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.get_recent_receipts_or_pantry(user_id=user_id, limit=limit)

    client = get_supabase_client()
    try:
        # 1. Prova prima con source_type = 'receipt'
        query = (
            client.table("items")
            .select("*")
            .eq("status", "active")
            .eq("source_type", "receipt")
        )
        if user_id != "all":
            query = query.eq("user_id", user_id)
        res = query.order("created_at", desc=True).limit(limit).execute()
        receipts = res.data or []

        # 2. Se pochi o nulli, cerca anche schede Cucina con subcategory contenente 'scontrino'
        if len(receipts) < limit:
            remaining = limit - len(receipts)
            query2 = (
                client.table("items")
                .select("*")
                .eq("status", "active")
                .eq("category", "Cucina & Alimentazione")
                .ilike("subcategory", "%scontrino%")
            )
            if user_id != "all":
                query2 = query2.eq("user_id", user_id)
            res2 = query2.order("created_at", desc=True).limit(remaining).execute()
            for r in (res2.data or []):
                if not any(x.get("id") == r.get("id") for x in receipts):
                    receipts.append(r)

        return receipts[:limit]
    except Exception as e:
        logger.error(f"Errore recupero scontrini/dispensa: {e}")
        return []


def get_random_educational_item(user_id: str = "default") -> Optional[Dict[str, Any]]:
    """
    Seleziona un elemento attivo salvato a scopo di ripasso / micro-learning (/pillola).
    Predilige categorie ad alto valore formativo: AI, Produttività, Life Hacks, Notizie, Cucina.
    """
    if settings.DB_PROVIDER == "sqlite":
        return sqlite_q.get_random_educational_item(user_id=user_id)

    client = get_supabase_client()
    try:
        categories = [
            "AI, Tech & Software",
            "Produttività, Finanza Personale & Business",
            "Life Hacks, Casa & Fai da Te",
            "Notizie, Attualità & Economia",
            "Cucina & Alimentazione",
            "Fitness, Sport & Salute",
        ]
        query = (
            client.table("items")
            .select("*")
            .eq("status", "active")
            .in_("category", categories)
        )
        if user_id != "all":
            query = query.eq("user_id", user_id)

        res = query.order("created_at", desc=True).limit(30).execute()
        items = res.data or []
        if not items:
            fallback_query = client.table("items").select("*").eq("status", "active")
            if user_id != "all":
                fallback_query = fallback_query.eq("user_id", user_id)
            res_fb = fallback_query.order("created_at", desc=True).limit(20).execute()
            items = res_fb.data or []

        if not items:
            return None

        import random
        return random.choice(items)
    except Exception as e:
        logger.error(f"Errore recupero pillola educativa: {e}")
        return None



