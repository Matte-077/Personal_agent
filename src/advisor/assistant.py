import json
import logging
import re
from typing import List, Dict, Any, Optional
from google.genai import types

from src.ai.gemini_client import GeminiClient
from src.config import settings
from src.db.queries import (
    search_semantic,
    search_fulltext,
    search_hybrid_rrf,
    search_by_ingredients,
    search_automotive,
    get_recent_items,
    get_recent_receipts_or_pantry,
)

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)

CONSULTATION_SYSTEM_PROMPT = """You are a consultative personal assistant acting as a digital second brain.
Your task is to answer the user's questions using the content stored in their personal database.

RESPONSE RULES:
1. BILINGUAL & LANGUAGE MIRRORING: Detect the language of the user's inquiry (Italian or English) and ALWAYS respond in the SAME language (if they ask in English, reply fluently in English; if in Italian, reply in Italian). Synthesize and cite saved items regardless of their original stored language.
2. Explicitly cite retrieved database items (mention title, author/source, or link if available).
3. Recipe & Ingredient Inquiries (e.g. "I have eggs and milk"): Suggest relevant saved recipes explaining how to use them and note any extra ingredients needed.
4. Vehicle & Listing Inquiries (e.g. BMW 330e): List key details (price, mileage, trim, laser headlights) and provide a concise comparison.
5. Certifications & Learning Inquiries: List exact names mentioned in saved items, highlight Tier Lists or rankings (e.g. Tier S, Tier A), pros/cons, and whether exams are proctored or simple certificates of completion.
6. Partial cards: If an item is labeled [PARTIAL CARD FROM URL], explain transparently that the link was saved but full text is not yet available, and invite the user to paste text. Do not hallucinate missing facts.
7. Fridge & Pantry Inquiries (e.g. 'what can I cook tonight?', 'what is in my fridge?'): Cross-reference recent grocery receipts with saved recipes to suggest meals that use up perishable items.
8. No relevant items: Transparently explain that no matching items were found in the database and suggest saving content on that topic.
"""


class AdvisorService:
    """
    Consultative engine interpreting user inquiries, querying the database
    via hybrid search (dense vectors + lexical filters) and synthesizing intelligent answers.
    """

    def __init__(self, ai_client: Optional[GeminiClient] = None):
        self._ai = ai_client

    @property
    def ai(self) -> Any:
        """Returns the AI client, lazily initializing if not already set."""
        if self._ai is None:
            if settings.AI_PROVIDER == "ollama":
                try:
                    from src.ai.ollama_client import OllamaClient
                    self._ai = OllamaClient()
                    return self._ai
                except Exception as e:
                    logger.warning(f"Automatic OllamaClient initialization for Advisor failed: {e}")
                    return None

            try:
                self._ai = GeminiClient()
            except Exception as e:
                logger.warning(f"Automatic GeminiClient initialization for Advisor failed: {e}")
                return None
        return self._ai

    @ai.setter
    def ai(self, client: Any) -> None:
        self._ai = client

    def detect_intent(self, text: str) -> str:
        """
        Detects message intent:
        - 'SAVE_URL': Contains a link to ingest
        - 'QUERY': A question or consultation inquiry
        - 'SAVE_NOTE': A personal note or reminder to catalogue
        """
        stripped = text.strip()
        if URL_REGEX.search(stripped):
            return "SAVE_URL"

        # 1. Domande esplicite con punto interrogativo
        if "?" in stripped:
            return "QUERY"

        # 2. Interrogativi diretti e comandi di ricerca/elenco
        search_command_pattern = (
            r"\b(cosa|quali|quale|chi|dove|quando|perché|quanto|quanti|quante)\b"
            r"|"
            r"\b(trova|trovami|cerca|cercami|mostra|mostrami|elenca|elencami|consiglia|consigliami|suggerisci|dimmi)\b"
        )
        if re.search(search_command_pattern, stripped, re.IGNORECASE):
            return "QUERY"

        # 3. Query frigo / ricette contestuali (senza '?', ma con chiaro intento svuota-frigo)
        fridge_cooking_patterns = [
            r"\b(in frigo|in dispensa)\b",
            r"\b(cosa (posso )?(cucinare|preparare|fare))\b",
            r"\bho\s+.*(in frigo|in dispensa|da consumare|da cucinare)\b",
            r"\b(idee? (per )?(cena|pranzo|colazione|ricetta))\b",
        ]
        for pattern in fridge_cooking_patterns:
            if re.search(pattern, stripped, re.IGNORECASE):
                return "QUERY"

        # 4. Query filtri annunci con criteri o soglie numeriche esplicite
        filter_query_patterns = [
            r"\b(sotto i|sotto ai|meno di|più di|superiore a|inferiore a)\s+\d+",
            r"\b(migliori?|consigliat[oiea])\s+(bmw|auto|ricett[ae]|tool|app|film|serie|ristorant[ie])\b",
        ]
        for pattern in filter_query_patterns:
            if re.search(pattern, stripped, re.IGNORECASE):
                return "QUERY"

        return "SAVE_NOTE"

    def retrieve_context(self, question: str, user_id: str = "default") -> List[Dict[str, Any]]:
        """
        Recupera gli elementi più rilevanti da Supabase tramite ricerca ibrida reale
        (Semantica Vettoriale + Full-Text Search in Italiano + Filtri Relazionali/JSONB).
        """
        retrieved_items: Dict[str, Dict[str, Any]] = {}
        lower_q = question.lower()

        # 1. Ricerca Ibrida RRF (Vettoriale semantica + Full-Text bilingue)
        try:
            q_emb = self.ai.generate_embedding(question) if self.ai else None
            hybrid_matches = search_hybrid_rrf(
                query_text=question,
                query_embedding=q_emb,
                user_id=user_id,
                limit=5,
            )
            for item in hybrid_matches:
                item_id = str(item.get("id"))
                if item_id:
                    retrieved_items[item_id] = item
        except Exception as e:
            logger.warning(f"Ricerca Ibrida RRF fallita ({e}), continuo con fallback.")
            if self.ai:
                try:
                    q_emb = self.ai.generate_embedding(question)
                    semantic_matches = search_semantic(
                        embedding=q_emb,
                        match_count=5,
                        match_threshold=settings.DEFAULT_MATCH_THRESHOLD,
                        user_id=user_id,
                    )
                    for item in semantic_matches:
                        retrieved_items[str(item["id"])] = item
                except Exception as e_sem:
                    logger.warning(f"Fallback semantico non riuscito: {e_sem}")

        # 3. Euristica Relazionale Cucina & Ingredienti (query nativa PostgreSQL)
        common_ingredients = [
            "uova", "uovo", "latte", "farina", "cioccolato", "burro", "zucchero",
            "pollo", "pomodoro", "pomodori", "pasta", "riso", "ricotta", "parmigiano",
            "spinaci", "zucchine", "tonno", "cipolla", "aglio", "olio"
        ]
        found_ings = [ing for ing in common_ingredients if ing in lower_q]
        if found_ings:
            try:
                ing_matches = search_by_ingredients(ingredients=found_ings, user_id=user_id, limit=3)
                for item in ing_matches:
                    item_id = str(item.get("id"))
                    if item_id:
                        retrieved_items[item_id] = item
            except Exception as e:
                logger.warning(f"Errore ricerca ingredienti in advisor: {e}")

        # 4. Euristica Dispensa / Svuota-Frigo & Scontrini Recenti
        fridge_keywords = ["frigo", "dispensa", "scad", "svuota", "in casa", "cosa cucino", "cosa preparo", "spesa", "cena", "pranzo"]
        if any(w in lower_q for w in fridge_keywords):
            try:
                recent_receipts = get_recent_receipts_or_pantry(user_id=user_id, limit=3)
                pantry_ings = []
                for r in recent_receipts:
                    r_id = str(r.get("id"))
                    if r_id:
                        retrieved_items[r_id] = r
                    r_meta = r.get("metadata") or {}
                    for ing in r_meta.get("ingredienti_principali") or []:
                        pantry_ings.append(str(ing).lower().strip())
                    for ing in r_meta.get("alimenti_deperibili") or []:
                        pantry_ings.append(str(ing).lower().strip())

                # Se ci sono alimenti in dispensa, cerchiamo ricette correlate per svuotare il frigo
                if pantry_ings:
                    distinct_ings = list(dict.fromkeys(pantry_ings))[:6]
                    matched_recipes = search_by_ingredients(ingredients=distinct_ings, user_id=user_id, limit=3)
                    for rec in matched_recipes:
                        rec_id = str(rec.get("id"))
                        if rec_id:
                            retrieved_items[rec_id] = rec
            except Exception as e:
                logger.warning(f"Errore recupero scontrini/dispensa in advisor: {e}")

        # 5. Euristica Relazionale Automotive (BMW, prezzi con filtro numerico nativo, laser)
        if any(w in lower_q for w in ["auto", "bmw", "330e", "g20", "g21", "macchina", "laser"]):
            # Estrazione prezzo legata a parole chiave per non confondersi con anni (2020-2024) o modelli (330)
            price_match = re.search(
                r"(?:sotto\s*(?:i)?|meno\s*di|fino\s*a|massimo|max|prezzo\s*<=?)\s*(\d{1,3}(?:[.\s]\d{3})*|\d+)\s*(?:€|euro)?",
                lower_q,
                re.IGNORECASE,
            ) or re.search(r"(\d{2,3}(?:[.\s]\d{3})*|\d{4,6})\s*(?:€|euro)", lower_q, re.IGNORECASE)

            max_p = None
            if price_match:
                try:
                    num_str = price_match.group(1).replace(".", "").replace(" ", "")
                    num = int(num_str)
                    if 5000 <= num <= 200000:
                        max_p = num
                except (ValueError, IndexError):
                    pass

            try:
                auto_matches = search_automotive(
                    max_price=max_p,
                    laser_lights=("laser" in lower_q),
                    g21_only=("g21" in lower_q or "touring" in lower_q),
                    user_id=user_id,
                    limit=3,
                )
                for item in auto_matches:
                    item_id = str(item.get("id"))
                    if item_id:
                        retrieved_items[item_id] = item
            except Exception as e:
                logger.warning(f"Errore ricerca automotive in advisor: {e}")

        return list(retrieved_items.values())

    def consult(self, question: str, user_id: str = "default") -> str:
        """
        Elabora la domanda, raccoglie il contesto da Supabase e formula la risposta finale.
        """
        logger.info(f"Elaborazione consultazione per user {user_id}: '{question}'")
        items = self.retrieve_context(question=question, user_id=user_id)

        # Preparazione sintesi contesto
        if not items:
            context_text = "Nessun elemento salvato nel database al momento."
        else:
            context_lines = []
            for i, it in enumerate(items, 1):
                meta = it.get("metadata") or {}
                url = it.get("source_url") or ""
                meta_str = json.dumps(meta, ensure_ascii=False)

                quality = meta.get("extraction", {}).get("quality") if isinstance(meta, dict) else None
                quality_tag = ""
                if quality == "link_only":
                    quality_tag = " [SCHEDA PARZIALE DA URL - Contenuto completo non ancora estratto]"
                elif quality == "partial":
                    quality_tag = " [SCHEDA PARZIALE - Estrazione parziale]"

                context_lines.append(
                    f"Elemento {i}{quality_tag}:\n"
                    f"- Titolo: {it.get('title')}\n"
                    f"- Categoria: {it.get('category')} ({it.get('subcategory')})\n"
                    f"- Sintesi: {it.get('summary')}\n"
                    f"- Metadati: {meta_str}\n"
                    f"- URL Fonte: {url}\n"
                )
            context_text = "\n".join(context_lines)

        prompt = (
            f"Domanda dell'utente:\n\"{question}\"\n\n"
            f"Contenuti trovati nel database personale dell'utente:\n\"\"\"\n{context_text}\n\"\"\"\n\n"
            "Formula una risposta colloquiale, utile e precisa citando i contenuti salvati pertinenti."
        )

        if not self.ai:
            return "⚠️ Il servizio AI di consultazione non è al momento disponibile."

        from src.ai.ollama_client import OllamaClient
        if isinstance(self.ai, OllamaClient):
            try:
                return self.ai.generate_response(
                    system_prompt=CONSULTATION_SYSTEM_PROMPT,
                    user_prompt=prompt,
                    temperature=0.4,
                )
            except Exception as e:
                logger.error(f"Errore consultazione Ollama: {e}")
                return "⚠️ Errore durante l'elaborazione con il modello AI locale."

        if not getattr(self.ai, "client", None):
            return "⚠️ Il servizio AI di consultazione non è al momento disponibile."

        config = types.GenerateContentConfig(
            system_instruction=CONSULTATION_SYSTEM_PROMPT,
            temperature=0.4,
        )

        response = self.ai.client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )

        return response.text.strip() if response.text else "Non sono riuscito a elaborare una risposta."
