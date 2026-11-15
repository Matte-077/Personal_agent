import asyncio
import html
import io
import logging
import re
import time
from typing import Optional, Any
from telegram import Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from src.config import settings
from src.bot.security import restricted, create_web_access_token
from src.bot.responses import (
    format_saved_item_card,
    build_item_card_keyboard,
    format_learning_pill,
    build_pill_keyboard,
)
from src.extractors import extract_from_url
from src.extractors.car_photos import process_and_upload_car_photos
from src.utils.image_compressor import compress_image_to_webp
from src.utils.tts import synthesize_speech
from src.db.storage import upload_car_photo
from src.ai.gemini_client import GeminiClient
from src.advisor.assistant import AdvisorService, URL_REGEX
from src.advisor.car_tco import calculate_import_tco
from src.db.queries import (
    save_item,
    soft_delete_item,
    get_item_by_id,
    find_active_items_by_keyword,
    get_recent_receipts_or_pantry,
    get_random_educational_item,
)
import httpx
from google.genai import types

logger = logging.getLogger(__name__)

MAX_MEDIA_FILE_SIZE = 20 * 1024 * 1024  # 20 MB limit per file inviati su Telegram

MULTIMODAL_TRANSCRIPTION_PROMPT = (
    "Analizza e trascrivi questo contenuto multimediale (audio/video/immagine) strutturando la risposta nelle seguenti 4 sezioni obbligatorie:\n\n"
    "1. TRASCRIZIONE FEDELE:\n"
    "Trascrivi il parlato e tutto il testo mostrato a schermo (titoli, slide, cartelli) nei minimi dettagli, senza riassunti o omissioni.\n\n"
    "2. ENTITÀ NOMINATE:\n"
    "Elenca ogni singolo nome proprio esatto citato o mostrato a video (es. nomi esatti di corsi, certificazioni, tool, modelli, brand, piattaforme). "
    "È severamente vietato raggrupparli con formule vaghe come 'varie certificazioni' o 'diversi corsi'.\n\n"
    "3. DETTAGLI PER ENTITÀ:\n"
    "Per ciascuna entità/corso citato specifica: argomento, gratuità/costi, se richiede esame sorvegliato (proctored) o rilascia solo attestato di frequenza, pro e contro e il verdetto dell'autore.\n\n"
    "4. CLASSIFICHE / TIER LIST:\n"
    "Se nel contenuto è presente un ranking, podio o una Tier List (es. Tier S, A, B, C, D), riportala integralmente con la posizione esatta di ogni elemento e la motivazione fornita nel video."
)

_ai_client: Any = None
_advisor: Optional[AdvisorService] = None


def get_ai_client() -> Any:
    """Inizializzazione lazy del client AI (Gemini o Ollama in locale)."""
    global _ai_client
    if _ai_client is None:
        if settings.AI_PROVIDER == "ollama":
            try:
                from src.ai.ollama_client import OllamaClient
                _ai_client = OllamaClient()
                return _ai_client
            except Exception as e:
                logger.error(f"Errore inizializzazione OllamaClient: {e}")
                return None

        try:
            if not settings.GEMINI_API_KEY:
                logger.warning("GEMINI_API_KEY non configurata: client AI non attivo.")
                return None
            _ai_client = GeminiClient()
        except Exception as e:
            logger.error(f"Errore inizializzazione GeminiClient: {e}")
            return None
    return _ai_client


def get_advisor() -> Optional[AdvisorService]:
    """Inizializzazione lazy dell'assistente consultivo."""
    global _advisor
    if _advisor is None:
        client = get_ai_client()
        if client is None:
            return None
        _advisor = AdvisorService(ai_client=client)
    return _advisor


def split_message_text(text: str, max_chars: int = 3900) -> list[str]:
    """
    Spezza un testo lungo su interruzioni di riga naturali (\n\n o \n)
    per non superare il limite perentorio di 4096 caratteri imposto da Telegram.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    lines = text.split("\n")
    current_chunk: list[str] = []
    current_length = 0

    for line in lines:
        line_len = len(line) + 1  # include il newline
        if current_length + line_len > max_chars:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_length = line_len
            else:
                # Singola riga che da sola supera max_chars: spezza per blocchi fissi
                for sub_i in range(0, len(line), max_chars):
                    chunks.append(line[sub_i : sub_i + max_chars])
                current_chunk = []
                current_length = 0
        else:
            current_chunk.append(line)
            current_length += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks or [text]


async def send_markdown_safe(message, text: str, reply_markup=None):
    """
    Invia uno o più messaggi Telegram in HTML con split automatico sotto i 3900 caratteri
    e fallback su testo semplice senza tag in caso di parsing error.
    Se presente, reply_markup viene allegato all'ultimo frammento della sequenza.
    """
    chunks = split_message_text(text, max_chars=3900)
    total_chunks = len(chunks)

    for i, chunk in enumerate(chunks):
        is_last = (i == total_chunks - 1)
        markup = reply_markup if is_last else None

        try:
            await message.reply_text(
                chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=markup,
            )
        except Exception as e:
            logger.warning(f"Fallback invio messaggio Telegram senza HTML ({e})")
            plain_text = re.sub(r"<[^>]+>", "", chunk)
            try:
                await message.reply_text(
                    plain_text,
                    disable_web_page_preview=True,
                    reply_markup=markup,
                )
            except Exception as e2:
                logger.error(f"Errore critico invio messaggio Telegram: {e2}")



@restricted
async def handle_start_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Risponde ai comandi /start e /help con una panoramica chiara delle funzionalità."""
    message = update.effective_message
    if not message:
        return
    help_text = (
        "👋 <b>Benvenuto nel tuo Agente Personale (Secondo Cervello)!</b>\n\n"
        "Ecco cosa puoi fare:\n"
        "• <b>Condividi qualsiasi link:</b> Reel di Instagram, annunci auto mobile.de, notizie web.\n"
        "• <b>Salva note e idee:</b> Invia promemoria testuali, messaggi vocali o foto.\n"
        "• <b>Fai domande:</b> Chiedi ad esempio:\n"
        "  - <i>'Ho uova e latte in frigo, cosa posso cucinare?'</i>\n"
        "  - <i>'Mostrami le BMW 330e salvate sotto i 35.000€ con fari laser'</i>\n"
        "  - <i>'Quali certificazioni mi consigli per la carriera?'</i>\n"
        "• <b>Elimina schede:</b> Clicca sul tasto <i>'🗑️ Elimina scheda'</i> sotto ogni elemento o usa <code>/elimina &lt;ricerca&gt;</code>.\n"
        "• <b>Hands-Free Vocale:</b> Invia un messaggio vocale con una domanda e il bot ti risponderà con una nota vocale sintetica!\n"
        "• <b>Micro-Learning:</b> Usa <code>/pillola</code> per ripassare a rotazione un consiglio pratico o un trucco tech/AI salvato.\n"
        "• <b>Dashboard &amp; Mini App:</b> Usa <code>/dashboard</code> per aprire la dashboard visiva con ricerca live e confronto auto.\n\n"
        "Tutto viene catalogato e salvato automaticamente nel tuo database privato Supabase."
    )
    await send_markdown_safe(message, help_text)



@restricted
async def handle_unsupported_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Informa l'utente sui formati non supportati (es. sticker, contatti, posizioni, documenti generici)."""
    message = update.effective_message
    if message:
        await message.reply_text(
            "ℹ️ Questo formato non è supportato. Puoi inviarmi link, note di testo, foto, audio/vocali o video."
        )


@restricted
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Gestore messaggi di testo Telegram.
    Riconosce se è un link, una domanda o una nota personale.
    """
    message = update.effective_message
    user = update.effective_user
    if not message or not message.text:
        return

    text = message.text.strip()
    user_id = str(user.id) if user else "default"

    advisor = get_advisor()
    ai_client = get_ai_client()
    if not advisor or not ai_client:
        await message.reply_text("⚠️ Il servizio AI non è al momento configurato o disponibile.")
        return

    # Rilevamento intento
    intent = advisor.detect_intent(text)

    # 1. Caso: Link da analizzare e salvare (Instagram, mobile.de, web)
    if intent == "SAVE_URL":
        match = URL_REGEX.search(text)
        url = match.group(0) if match else text
        status_msg = await message.reply_text("⏳ *Analisi in corso...* Estraggo il contenuto.", parse_mode=ParseMode.MARKDOWN)

        try:
            # Estrazione contenuto tramite la pipeline specializzata
            extracted = await asyncio.wait_for(extract_from_url(url), timeout=25.0)
            raw_text = extracted.get("raw_text", url)
            source_type = extracted.get("source_type", "web_article")

            extraction_info = extracted.get("extraction") or {}
            quality = extraction_info.get("quality", "full")

            # Se l'utente ha aggiunto un commento oltre al link, lo uniamo
            extra_comment = URL_REGEX.sub("", text).strip()
            if extra_comment:
                raw_text = f"Nota utente: {extra_comment}\n\n{raw_text}"

            # Analisi multimodale video (Reel Instagram, TikTok, YouTube Shorts con media_url disponibile)
            media_url = extracted.get("media_url")
            is_video_source = (
                source_type == "instagram"
                or extracted.get("is_video", False)
                or extracted.get("video_platform") in ("tiktok", "youtube_shorts", "youtube")
            )
            if media_url and is_video_source:
                try:
                    await status_msg.edit_text("🎬 *Scansione video...* Analizzo fotogrammi e audio con Gemini.", parse_mode=ParseMode.MARKDOWN)
                    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                        resp = await client.get(media_url, headers={"User-Agent": "Mozilla/5.0"})
                        if resp.status_code == 200 and len(resp.content) <= MAX_MEDIA_FILE_SIZE:
                            video_bytes = resp.content
                            prompt = MULTIMODAL_TRANSCRIPTION_PROMPT
                            caption = extracted.get("caption") or ""
                            if caption:
                                prompt += f"\n\nDidascalia del post: {caption}"
                            if extra_comment:
                                prompt += f"\n\nNota utente allegata: {extra_comment}"

                            part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")
                            mm_response = await asyncio.wait_for(
                                asyncio.to_thread(
                                    ai_client.client.models.generate_content,
                                    model=settings.GEMINI_MODEL,
                                    contents=[part, prompt],
                                ),
                                timeout=40.0,
                            )
                            if mm_response.text:
                                raw_text = mm_response.text
                                extraction_info["quality"] = "full"
                                logger.info(f"Analisi multimodale video completata per link: {url}")
                except Exception as e:
                    logger.warning(f"Download/analisi multimodale video fallita per {url} ({e}), continuo con metadati testuali.")

            if quality == "link_only":
                await status_msg.edit_text("⚠️ *Sito protetto (429/antibot).* Scheda parziale da URL...", parse_mode=ParseMode.MARKDOWN)
            else:
                await status_msg.edit_text("🧠 *Comprensione AI...* Categorizzo con Gemini Flash Lite.", parse_mode=ParseMode.MARKDOWN)

            # Classificazione ed embedding in thread separato
            record = await asyncio.wait_for(
                asyncio.to_thread(
                    ai_client.process_item,
                    raw_text=raw_text,
                    source_type=source_type,
                    source_url=url,
                    user_id=user_id,
                    extraction=extraction_info,
                ),
                timeout=35.0,
            )

            # Se rilevata specifica piattaforma video (TikTok, YouTube Shorts), la annotiamo nei metadata
            if extracted.get("video_platform"):
                if "metadata" not in record or not isinstance(record["metadata"], dict):
                    record["metadata"] = {}
                record["metadata"]["piattaforma"] = extracted["video_platform"]

            # Gestione foto per annunci auto (mobile.de) e calcolo TCO Importazione (DE -> IT)
            if record.get("category") == "Automotive & Annunci Auto":
                meta = record.get("metadata") or {}
                car_price = meta.get("prezzo_eur") or extracted.get("price_eur")
                paese = str(meta.get("paese_venditore") or "").lower()
                is_de = "mobile.de" in url or "germania" in paese or "de" in paese or not paese
                if car_price and is_de:
                    tco = calculate_import_tco(
                        price_eur=car_price,
                        car_model=meta.get("modello") or meta.get("carrozzeria_generazione") or record.get("title"),
                        seller_country="DE",
                    )
                    if tco:
                        if "metadata" not in record or not isinstance(record["metadata"], dict):
                            record["metadata"] = {}
                        record["metadata"]["tco_importazione"] = tco

                images = extracted.get("images") or []
                if images:
                    await status_msg.edit_text("📸 *Ottimizzazione immagini...* Comprimo e archivio le foto WebP.", parse_mode=ParseMode.MARKDOWN)
                    photo_urls = await process_and_upload_car_photos(images, user_text=text, user_id=user_id)
                    if photo_urls:
                        if "metadata" not in record or not isinstance(record["metadata"], dict):
                            record["metadata"] = {}
                        record["metadata"]["foto_urls"] = photo_urls

            # Salvataggio su Supabase in thread separato
            saved_item = await asyncio.to_thread(save_item, record)

            # Risposta con scheda formattata ed eventuale album fotografico
            card_text = format_saved_item_card(record)
            item_id = str(saved_item.get("id")) if isinstance(saved_item, dict) and saved_item.get("id") else None
            reply_markup = build_item_card_keyboard(item_id, category=record.get("category"))
            await status_msg.delete()

            foto_urls = record.get("metadata", {}).get("foto_urls") if isinstance(record.get("metadata"), dict) else []
            if foto_urls:
                try:
                    media_group = [InputMediaPhoto(media=u) for u in foto_urls[:2]]
                    await message.reply_media_group(media=media_group)
                except Exception as e:
                    logger.warning(f"Errore invio media group foto Telegram: {e}")

            await send_markdown_safe(message, card_text, reply_markup=reply_markup)

            if extracted.get("cookie_expired"):
                try:
                    await message.reply_text(
                        "⚠️ I cookie dell'account Instagram burner risultano scaduti "
                        "o invalidati da Meta. Ricordati di rinnovarli su Render "
                        "(IG_SESSIONID / INSTAGRAM_COOKIES)."
                    )
                except Exception as e_notify:
                    logger.warning(f"Avviso scadenza cookie non inviato: {e_notify}")

            if quality == "link_only" and context and hasattr(context, "user_data") and context.user_data is not None:
                context.user_data["last_partial_item"] = {
                    "url": url,
                    "title": record.get("title", ""),
                    "timestamp": time.time(),
                }
                logger.info(f"Memorizzato last_partial_item in context.user_data per arricchimento: {url}")

        except Exception as e:
            logger.error(f"Errore durante l'elaborazione del link {url}: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Si è verificato un errore durante l'elaborazione: {e}")

    # 2. Caso: Domanda o consultazione del database
    elif intent == "QUERY":
        status_msg = await message.reply_text("🔍 *Consulto il tuo secondo cervello...*", parse_mode=ParseMode.MARKDOWN)
        try:
            answer = await asyncio.wait_for(
                asyncio.to_thread(advisor.consult, question=text, user_id=user_id),
                timeout=35.0,
            )
            await status_msg.delete()
            await send_markdown_safe(message, answer)
        except Exception as e:
            logger.error(f"Errore durante la consultazione: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Errore durante la consultazione: {e}")

    # 3. Caso: Nota testuale / Promemoria / Arricchimento scheda parziale
    else:
        # Verifica se il messaggio è un arricchimento per una scheda parziale recente
        last_partial = None
        if context and hasattr(context, "user_data") and context.user_data:
            last_partial = context.user_data.get("last_partial_item")

        is_reply = bool(message.reply_to_message)
        is_enrichment = False
        if last_partial and isinstance(last_partial, dict):
            time_diff = time.time() - last_partial.get("timestamp", 0)
            if is_reply or (time_diff < 600 and len(text) > 30):
                is_enrichment = True

        if is_enrichment and last_partial:
            target_url = last_partial["url"]
            target_title = last_partial.get("title", "")
            logger.info(f"Rilevato arricchimento testuale per scheda parziale URL: {target_url}")
            status_msg = await message.reply_text("🔄 *Arricchimento in corso...* Integro il testo nella scheda salvata.", parse_mode=ParseMode.MARKDOWN)
            try:
                enriched_raw = f"{target_title}\n\n{text}"
                record = await asyncio.wait_for(
                    asyncio.to_thread(
                        ai_client.process_item,
                        raw_text=enriched_raw,
                        source_type="web_article",
                        source_url=target_url,
                        user_id=user_id,
                        extraction={"tier": "user_enrichment", "quality": "full", "http_status": 200},
                        quality="full",
                    ),
                    timeout=35.0,
                )
                saved_item = await asyncio.to_thread(save_item, record)
                context.user_data.pop("last_partial_item", None)
                card_text = format_saved_item_card(record)
                item_id = str(saved_item.get("id")) if isinstance(saved_item, dict) and saved_item.get("id") else None
                reply_markup = build_item_card_keyboard(item_id, category=record.get("category"))
                await status_msg.delete()
                await send_markdown_safe(message, f"🎉 *Scheda arricchita con successo!*\n\n{card_text}", reply_markup=reply_markup)
                return
            except Exception as e:
                logger.error(f"Errore durante l'arricchimento della scheda {target_url}: {e}", exc_info=True)
                await status_msg.edit_text(f"❌ Errore durante l'arricchimento: {e}")
                return

        # Normale salvataggio nota testuale
        status_msg = await message.reply_text("💾 *Salvataggio nota...*", parse_mode=ParseMode.MARKDOWN)
        try:
            record = await asyncio.wait_for(
                asyncio.to_thread(
                    ai_client.process_item,
                    raw_text=text,
                    source_type="text_note",
                    user_id=user_id,
                ),
                timeout=35.0,
            )
            saved_item = await asyncio.to_thread(save_item, record)
            card_text = format_saved_item_card(record)
            item_id = str(saved_item.get("id")) if isinstance(saved_item, dict) and saved_item.get("id") else None
            reply_markup = build_item_card_keyboard(item_id, category=record.get("category"))
            await status_msg.delete()
            await send_markdown_safe(message, card_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Errore durante il salvataggio della nota: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Errore durante il salvataggio: {e}")


@restricted
async def handle_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Tier 0: Gestione nativa di note vocali, audio e video inoltrati direttamente in chat.
    Bypassa lo scraping web e invia i byte direttamente all'analisi multimodale di Gemini.
    """
    message = update.effective_message
    user = update.effective_user
    if not message:
        return

    user_id = str(user.id) if user else "default"

    ai_client = get_ai_client()
    if not ai_client:
        await message.reply_text("⚠️ Il servizio AI non è configurato.")
        return

    # Controllo preventivo dimensione file Telegram (guard 20MB)
    target_media = message.voice or message.audio or message.video or (message.photo[-1] if message.photo else None)
    target_size = getattr(target_media, "file_size", None)
    if isinstance(target_size, int) and target_size > MAX_MEDIA_FILE_SIZE:
        mb_size = target_size // (1024 * 1024)
        await message.reply_text(f"⚠️ Il file è troppo grande ({mb_size} MB). Il limite massimo è di 20 MB.")
        return

    status_msg = await message.reply_text("🎙️ *Elaborazione media nativo (Tier 0)...*", parse_mode=ParseMode.MARKDOWN)

    try:
        media_file = None
        mime_type = "audio/ogg"
        source_type = "voice"

        if message.voice:
            media_file = await message.voice.get_file()
            mime_type = "audio/ogg"
            source_type = "voice"
        elif message.audio:
            media_file = await message.audio.get_file()
            mime_type = message.audio.mime_type or "audio/mp3"
            source_type = "voice"
        elif message.video:
            media_file = await message.video.get_file()
            mime_type = message.video.mime_type or "video/mp4"
            source_type = "instagram"
        elif message.photo:
            media_file = await message.photo[-1].get_file()
            mime_type = "image/jpeg"
            source_type = "image"

        if not media_file:
            await status_msg.edit_text("Formato media non supportato.")
            return

        # Controllo secondario dimensione file da metadati Telegram File
        file_size = getattr(media_file, "file_size", None)
        if isinstance(file_size, int) and file_size > MAX_MEDIA_FILE_SIZE:
            mb_size = file_size // (1024 * 1024)
            await status_msg.edit_text(f"⚠️ Il file è troppo grande ({mb_size} MB). Il limite massimo è di 20 MB.")
            return

        # Download dei byte in memoria
        media_bytes_io = io.BytesIO()
        await media_file.download_to_memory(media_bytes_io)
        media_bytes = media_bytes_io.getvalue()

        # Controllo terziario a difesa in profondità sulla dimensione effettiva scaricata
        if len(media_bytes) > MAX_MEDIA_FILE_SIZE:
            mb_size = len(media_bytes) // (1024 * 1024)
            await status_msg.edit_text(f"⚠️ Il file supera il limite massimo di 20 MB ({mb_size} MB scaricati).")
            return

        caption = message.caption or ""
        if message.photo:
            prompt = (
                "Sei un assistente visivo ed esperto di spesa e dispensa domestica.\n"
                "Esamina con cura l'immagine fornita:\n\n"
                "CASO 1: SE L'IMMAGINE È UNO SCONTRINO O RICEVUTA DI SUPERMERCATO/NEGOZIO:\n"
                "- Identifica l'insegna o supermercato (es. Esselunga, Coop, Conad, Lidl, Carrefour, Despar, ecc.).\n"
                "- Estrai la data dello scontrino (YYYY-MM-DD se visibile).\n"
                "- Estrai il totale della spesa in euro.\n"
                "- Elenca TUTTI i prodotti alimentari acquistati, normalizzando i nomi comuni (es. 'ricotta', 'petto di pollo', 'spinaci', 'latte', 'uova', 'pasta').\n"
                "- Evidenzia quali alimenti sono freschi o deperibili (latticini, carne fresca, pesce, verdure fresche) da consumare entro pochi giorni.\n\n"
                "CASO 2: SE È UN ALTRO TIPO DI FOTO O DOCUMENTO:\n"
                "- Trascrivi e descrivi fedelmente testi, titoli, slide ed entità visive salienti in modo strutturato.\n"
            )
        else:
            prompt = (
                "Analizza e trascrivi questo contenuto multimediale (audio/video/immagine) strutturando la risposta nelle seguenti 4 sezioni obbligatorie:\n\n"
                "1. TRASCRIZIONE FEDELE:\n"
                "Trascrivi il parlato e tutto il testo mostrato a schermo (titoli, slide, cartelli) nei minimi dettagli, senza riassunti o omissioni.\n\n"
                "2. ENTITÀ NOMINATE:\n"
                "Elenca ogni singolo nome proprio esatto citato o mostrato a video (es. nomi esatti di corsi, certificazioni, tool, modelli, brand, piattaforme). "
                "È severamente vietato raggrupparli con formule vaghe come 'varie certificazioni' o 'diversi corsi'.\n\n"
                "3. DETTAGLI PER ENTITÀ:\n"
                "Per ciascuna entità/corso citato specifica: argomento, gratuità/costi, se richiede esame sorvegliato (proctored) o rilascia solo attestato di frequenza, pro e contro e il verdetto dell'autore.\n\n"
                "4. CLASSIFICHE / TIER LIST:\n"
                "Se nel contenuto è presente un ranking, podio o una Tier List (es. Tier S, A, B, C, D), riportala integralmente con la posizione esatta di ogni elemento e la motivazione fornita nel video."
            )
        if caption:
            prompt += f"\n\nDidascalia utente allegata: {caption}"

        # Analisi multimodale diretta con Gemini in thread separato
        part = types.Part.from_bytes(data=media_bytes, mime_type=mime_type)
        response = await asyncio.wait_for(
            asyncio.to_thread(
                ai_client.client.models.generate_content,
                model=settings.GEMINI_MODEL,
                contents=[part, prompt],
            ),
            timeout=40.0,
        )
        transcribed_text = response.text or caption or "Contenuto multimediale"

        # Hands-Free Voice Assistant: Se è una nota vocale con intento consultivo (domanda), risponde vocalmente
        is_voice_message = (message.voice is not None or message.audio is not None)
        advisor = get_advisor()
        if is_voice_message and advisor:
            voice_intent = advisor.detect_intent(transcribed_text)
            if voice_intent == "QUERY":
                await status_msg.edit_text("🎙️ *Elaborazione risposta vocale...* Consulto il database.", parse_mode=ParseMode.MARKDOWN)
                answer_text = await asyncio.to_thread(advisor.consult, transcribed_text, user_id=user_id)
                await status_msg.delete()

                # Sintesi vocale audio neurale con edge-tts (hands-free in mobilità)
                try:
                    speech_bytes = await synthesize_speech(answer_text)
                    if speech_bytes:
                        await message.reply_voice(voice=io.BytesIO(speech_bytes))
                except Exception as e_tts:
                    logger.warning(f"Sintesi/invio nota vocale fallito ({e_tts}), invio testo.")

                await send_markdown_safe(message, f"🎙️ <i>Risposta al vocale:</i>\n\n{answer_text}")
                return

        # Classificazione in thread separato
        record = await asyncio.wait_for(
            asyncio.to_thread(
                ai_client.process_item,
                raw_text=transcribed_text,
                source_type=source_type,
                user_id=user_id,
            ),
            timeout=35.0,
        )

        # Se è uno scontrino della spesa, impostiamo source_type='receipt' per il tracciamento dispensa
        if message.photo:
            meta = record.get("metadata") or {}
            is_receipt = (
                record.get("category") == "Cucina & Alimentazione"
                and (
                    "scontrino" in str(record.get("subcategory", "")).lower()
                    or meta.get("supermercato")
                    or meta.get("totale_spesa_eur")
                )
            )
            if is_receipt:
                record["source_type"] = "receipt"

            try:
                compressed_webp = await asyncio.to_thread(
                    compress_image_to_webp, media_bytes, max_size=(1024, 768), quality=75
                )
                if compressed_webp:
                    photo_url = await asyncio.to_thread(upload_car_photo, compressed_webp, user_id=user_id)
                    if photo_url:
                        if "metadata" not in record or not isinstance(record["metadata"], dict):
                            record["metadata"] = {}
                        record["metadata"]["foto_urls"] = [photo_url]
            except Exception as e:
                logger.warning(f"Errore compressione/upload foto utente: {e}")

        saved_item = await asyncio.to_thread(save_item, record)

        card_text = format_saved_item_card(record)
        item_id = str(saved_item.get("id")) if isinstance(saved_item, dict) and saved_item.get("id") else None
        reply_markup = build_item_card_keyboard(item_id, category=record.get("category"))
        await status_msg.delete()
        await send_markdown_safe(message, card_text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Errore elaborazione media nativo: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Errore durante l'elaborazione del file: {e}")


@restricted
async def handle_elimina_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /elimina [keyword]: cerca tra le schede attive e permette l'eliminazione/archiviazione guidata.
    Se eseguito come reply a un messaggio del bot, propone l'eliminazione di quell'elemento.
    """
    message = update.effective_message
    user = update.effective_user
    if not message:
        return
    user_id = str(user.id) if user else "default"

    args = context.args or []
    query_text = " ".join(args).strip()

    # 1. Se è una reply a un messaggio con scheda
    if not query_text and message.reply_to_message:
        replied = message.reply_to_message.text or ""
        first_line = replied.split("\n", 1)[0].replace("✅", "").replace("⚠️", "").replace("📌", "").strip()
        candidates = await asyncio.to_thread(find_active_items_by_keyword, first_line[:40], user_id=user_id, limit=3)
        if candidates:
            item = candidates[0]
            item_id = item["id"]
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Sì, elimina", callback_data=f"confirm_del:{item_id}"),
                    InlineKeyboardButton("❌ Annulla", callback_data="cancel_del_cmd"),
                ]
            ])
            await message.reply_text(
                f"🗑️ Vuoi eliminare questo elemento dal tuo database?\n\n"
                f"📌 <b>{html.escape(item.get('title', 'Senza titolo'))}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            return

    if not query_text:
        await message.reply_text(
            "ℹ️ <b>Come eliminare un elemento dal database:</b>\n"
            "• Scrivi <code>/elimina &lt;parola chiave&gt;</code> (es. <code>/elimina bmw</code> o <code>/elimina certificazioni</code>)\n"
            "• Oppure premi il tasto <i>'🗑️ Elimina scheda'</i> sotto qualsiasi scheda salvata\n"
            "• Oppure rispondi con <code>/elimina</code> al messaggio della scheda che vuoi rimuovere.",
            parse_mode=ParseMode.HTML,
        )
        return

    candidates = await asyncio.to_thread(find_active_items_by_keyword, query_text, user_id=user_id, limit=5)
    if not candidates:
        await message.reply_text(
            f"🔍 Nessun elemento attivo trovato per: <i>'{html.escape(query_text)}'</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    if len(candidates) == 1:
        item = candidates[0]
        item_id = item["id"]
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Sì, elimina", callback_data=f"confirm_del:{item_id}"),
                InlineKeyboardButton("❌ Annulla", callback_data="cancel_del_cmd"),
            ]
        ])
        await message.reply_text(
            f"Trovato 1 elemento per <i>'{html.escape(query_text)}'</i>:\n\n"
            f"📌 <b>{html.escape(item.get('title', 'Senza titolo'))}</b> (<i>{html.escape(item.get('category', ''))}</i>)\n\n"
            "Confermi l'eliminazione dal database?",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    # Più elementi trovati
    buttons = []
    for i, c in enumerate(candidates, 1):
        c_id = c["id"]
        title_preview = (c.get("title") or "Senza titolo")[:32]
        buttons.append([InlineKeyboardButton(f"🗑️ {i}. {title_preview}", callback_data=f"ask_del:{c_id}")])
    buttons.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_del_cmd")])

    await message.reply_text(
        f"🔍 Trovati {len(candidates)} elementi per <i>'{html.escape(query_text)}'</i>. Quale desideri eliminare?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@restricted
async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce le interazioni con i pulsanti inline per la cancellazione soft-delete."""
    query = update.callback_query
    if not query or not query.data:
        return
    user = update.effective_user
    user_id = str(user.id) if user else "default"
    data = query.data

    if data == "cancel_del_cmd":
        await query.answer("Operazione annullata.")
        try:
            await query.edit_message_text("❌ Eliminazione annullata.")
        except Exception:
            pass
        return

    if data.startswith("ask_del:"):
        item_id = data.split(":", 1)[1]
        confirm_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Sì, elimina", callback_data=f"confirm_del:{item_id}"),
                InlineKeyboardButton("❌ Annulla", callback_data=f"cancel_del:{item_id}"),
            ]
        ])
        await query.answer()
        try:
            await query.edit_message_reply_markup(reply_markup=confirm_kb)
        except Exception as e:
            logger.debug(f"Modifica markup callback fallita: {e}")
        return

    if data.startswith("cancel_del:"):
        item_id = data.split(":", 1)[1]
        item = await asyncio.to_thread(get_item_by_id, item_id, user_id=user_id)
        cat = item.get("category") if item else None
        orig_kb = build_item_card_keyboard(item_id, category=cat)
        await query.answer("Eliminazione annullata.")
        try:
            await query.edit_message_reply_markup(reply_markup=orig_kb)
        except Exception as e:
            logger.debug(f"Ripristino markup callback fallito: {e}")
        return

    if data.startswith("shop_list:"):
        item_id = data.split(":", 1)[1]
        item = await asyncio.to_thread(get_item_by_id, item_id, user_id=user_id)
        if not item:
            await query.answer("Scheda non trovata o rimossa.", show_alert=True)
            return

        meta = item.get("metadata") or {}
        ingredients = meta.get("ingredienti_principali") or []
        title = item.get("title") or "Ricetta"

        # Recupera la dispensa e gli scontrini recenti dell'utente
        pantry_records = await asyncio.to_thread(get_recent_receipts_or_pantry, user_id=user_id, limit=5)
        pantry_ingredients = set()
        for p in pantry_records:
            p_meta = p.get("metadata") or {}
            for ing in p_meta.get("ingredienti_principali") or []:
                pantry_ingredients.add(str(ing).lower().strip())
            for ing in p_meta.get("alimenti_deperibili") or []:
                pantry_ingredients.add(str(ing).lower().strip())

        lines = [
            f"🛒 <b>Lista della Spesa per:</b> {html.escape(title)}",
            "━━━━━━━━━━━━━━━━━━",
        ]

        if not ingredients:
            lines.append("<i>Nessun ingrediente specifico registrato in questa scheda.</i>")
        else:
            to_buy = []
            already_have = []
            for ing in ingredients:
                ing_clean = str(ing).strip()
                if ing_clean.lower() in pantry_ingredients:
                    already_have.append(ing_clean)
                else:
                    to_buy.append(ing_clean)

            if to_buy:
                lines.append("<b>Da acquistare:</b>")
                for ing in to_buy:
                    lines.append(f"▫️ {html.escape(ing)}")

            if already_have:
                lines.append("")
                lines.append("<b>Già presenti in dispensa / frigo:</b>")
                for ing in already_have:
                    lines.append(f"✅ {html.escape(ing)} <i>(rilevato da scontrini recenti)</i>")

        lines.extend([
            "",
            "💡 <i>Copia o spunta questa lista per fare la spesa!</i>"
        ])

        checklist_text = "\n".join(lines)
        await query.answer("Lista della spesa generata!")
        if query.message:
            await query.message.reply_text(checklist_text, parse_mode=ParseMode.HTML)
        return

    if data.startswith("confirm_del:"):
        item_id = data.split(":", 1)[1]
        success = await asyncio.to_thread(soft_delete_item, item_id, user_id=user_id)
        if success:
            await query.answer("🗑️ Scheda eliminata con successo!", show_alert=True)
            try:
                await query.edit_message_reply_markup(reply_markup=None)
                if query.message:
                    await query.message.reply_text("🗑️ <i>Scheda eliminata dal database personale.</i>", parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.debug(f"Notifica cancellazione callback: {e}")
        else:
            await query.answer("⚠️ Impossibile eliminare l'elemento o già rimosso.", show_alert=True)
        return

    if data == "next_pillola":
        item = await asyncio.to_thread(get_random_educational_item, user_id=user_id)
        if not item:
            await query.answer("Nessun'altra scheda disponibile.", show_alert=True)
            return

        pill_text = format_learning_pill(item)
        reply_markup = build_pill_keyboard()
        await query.answer("Nuova pillola!")
        try:
            await query.edit_message_text(
                pill_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
        except Exception:
            if query.message:
                await send_markdown_safe(query.message, pill_text, reply_markup=reply_markup)
        return


@restricted
async def handle_pillola_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /pillola: estrae una scheda formativa casuale per il micro-learning / ripasso."""
    message = update.effective_message
    user = update.effective_user
    if not message:
        return
    user_id = str(user.id) if user else "default"

    item = await asyncio.to_thread(get_random_educational_item, user_id=user_id)
    if not item:
        await message.reply_text(
            "ℹ️ Non ci sono ancora abbastanza schede formative nel database.\n"
            "Salva contenuti su Tech, AI, Produttività o Life Hacks per iniziare il ripasso!",
            parse_mode=ParseMode.HTML,
        )
        return

    pill_text = format_learning_pill(item)
    reply_markup = build_pill_keyboard()
    await send_markdown_safe(message, pill_text, reply_markup=reply_markup)


@restricted
async def handle_dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /dashboard o /app: genera l'accesso alla Telegram Mini App o al Web Dashboard."""
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    base_url = settings.WEBHOOK_URL.rstrip('/') if settings.WEBHOOK_URL else f"http://localhost:{settings.PORT}"
    app_url = f"{base_url}/app"
    token = create_web_access_token(user.id, settings.TELEGRAM_BOT_TOKEN or "secret")
    desktop_url = f"{app_url}?token={token}"

    keyboard = []
    if app_url.startswith("https://"):
        keyboard.append([InlineKeyboardButton("📱 Apri Mini App (Telegram)", web_app=WebAppInfo(url=app_url))])
        keyboard.append([InlineKeyboardButton("💻 Apri su Browser Desktop", url=desktop_url)])
    else:
        keyboard.append([InlineKeyboardButton("💻 Apri Dashboard Locale (Browser)", url=desktop_url)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    caption = (
        "📊 <b>Dashboard &amp; Visual Workspace</b>\n\n"
        "Accedi alla tua dashboard interattiva:\n"
        "• 🔍 <b>Ricerca istantanea</b> &amp; filtri per categoria\n"
        "• ⚖️ <b>Matrice di confronto affiancato</b> (auto BMW 330e, ricette, tool)\n"
        "• 🇮🇹 <b>Costi su strada IT &amp; TCO calcolati</b>\n"
        "• 🛒 <b>Monitoraggio scadenze spesa &amp; eliminazione schede</b>\n\n"
        "Clicca in basso per aprirla subito dentro Telegram o sul tuo browser desktop (link protetto valido 48h):"
    )
    await message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)




