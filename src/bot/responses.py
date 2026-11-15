import html
from typing import Dict, Any, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def build_item_card_keyboard(item_id: Optional[str], category: Optional[str] = None) -> Optional[InlineKeyboardMarkup]:
    """Crea la tastiera inline con azioni rapide (es. Lista spesa per ricette) ed Elimina per una scheda salvata."""
    if not item_id:
        return None
    buttons = []
    if category == "Cucina & Alimentazione":
        buttons.append([InlineKeyboardButton("🛒 Crea Lista Spesa", callback_data=f"shop_list:{item_id}")])
    buttons.append([InlineKeyboardButton("🗑️ Elimina scheda", callback_data=f"ask_del:{item_id}")])
    return InlineKeyboardMarkup(buttons)

CATEGORY_EMOJIS = {
    "Automotive & Annunci Auto": "🚗",
    "Cucina & Alimentazione": "🍳",
    "AI, Tech & Software": "🤖",
    "Notizie, Attualità & Economia": "📰",
    "Fitness, Sport & Salute": "🏋️",
    "Produttività, Finanza Personale & Business": "💼",
    "Viaggi, Ristoranti & Luoghi": "✈️",
    "Media, Film, Libri & Podcast": "🎬",
    "Life Hacks, Casa & Fai da Te": "💡",
    "Altro / Varie & Non Classificato": "📦",
}


def _normalize_meta_field(val: Any) -> str:
    """Estrae in modo sicuro una rappresentazione testuale da stringhe, liste o dizionari."""
    if not val:
        return ""
    if isinstance(val, list):
        return "\n".join(str(x) for x in val if x).strip()
    if isinstance(val, dict):
        return "\n".join(f"- {k}: {v}" for k, v in val.items() if v).strip()
    return str(val).strip()


def format_saved_item_card(item: Dict[str, Any]) -> str:
    """
    Formatta una scheda Telegram completa con la dicitura di conferma 'Aggiunto al database'
    e il feedback analitico dettagliato per ogni categoria di contenuto in formato HTML robusto.
    """
    category = item.get("category", "Altro / Varie & Non Classificato")
    subcategory = item.get("subcategory", "")
    emoji = CATEGORY_EMOJIS.get(category, "📌")
    title = item.get("title", "Nuovo Contenuto")
    summary = item.get("summary", "")
    metadata = item.get("metadata") or {}
    tags = item.get("tags") or []
    source_url = item.get("source_url")
    confidence = item.get("confidence")

    esc_title = html.escape(str(title))
    esc_summary = html.escape(str(summary))
    esc_category = html.escape(str(category))
    sub_label = f" » <i>{html.escape(str(subcategory))}</i>" if subcategory else ""

    extraction = metadata.get("extraction") if isinstance(metadata, dict) else {}
    quality = extraction.get("quality") if isinstance(extraction, dict) else None

    if quality == "link_only":
        header = "⚠️ <b>Sito protetto (429/antibot). Scheda parziale da slug/URL</b>"
    elif quality == "partial":
        header = "ℹ️ <b>Scheda parziale (anteprima web/didascalia sintetica)</b>"
    else:
        header = "✅ <b>Aggiunto al database con successo!</b>"

    lines = [
        header,
        "━━━━━━━━━━━━━━━━━━",
        f"{emoji} <b>{esc_title}</b>",
        f"📂 <b>Categoria:</b> {esc_category}{sub_label}",
    ]

    if confidence is not None:
        lines.append(f"🎯 <b>Accuratezza AI:</b> {int(float(confidence) * 100)}%")

    lines.extend([
        "",
        f"📝 <b>Sintesi Analisi:</b>\n{esc_summary}",
    ])

    # Informazioni specifiche estratte per categoria
    meta_lines = []

    # 1. Automotive
    if category == "Automotive & Annunci Auto":
        tco = metadata.get("tco_importazione")
        if tco and isinstance(tco, dict):
            prezzo_base = tco.get("prezzo_base_eur")
            prezzo_finito = tco.get("prezzo_finito_eur")
            spese = tco.get("spese_import_totale_eur")
            if prezzo_base:
                meta_lines.append(f"🇩🇪 <b>Prezzo DE:</b> {prezzo_base:,} €".replace(",", "."))
            if prezzo_finito and spese:
                meta_lines.append(f"🇮🇹 <b>Chiavi in mano (IT):</b> ~{prezzo_finito:,} € <i>(+~{spese:,}€ bisarca, nazionalizzazione & targhe)</i>".replace(",", "."))
            if tco.get("superbollo_esente"):
                meta_lines.append("🛡️ <b>Superbollo:</b> Esente (PHEV 135 kW termici)")
        elif metadata.get("prezzo_eur"):
            try:
                prezzo_val = int(float(str(metadata['prezzo_eur']).replace('.', '').replace('€', '').replace(' ', '')))
                meta_lines.append(f"💰 <b>Prezzo:</b> {prezzo_val:,} €".replace(",", "."))
            except Exception:
                meta_lines.append(f"💰 <b>Prezzo:</b> {html.escape(str(metadata['prezzo_eur']))}")
        if metadata.get("chilometraggio_km"):
            try:
                km_val = int(float(str(metadata['chilometraggio_km']).replace('.', '').replace(' ', '')))
                meta_lines.append(f"🛣️ <b>Chilometri:</b> {km_val:,} km".replace(",", "."))
            except Exception:
                meta_lines.append(f"🛣️ <b>Chilometri:</b> {html.escape(str(metadata['chilometraggio_km']))}")
        if metadata.get("carrozzeria_generazione"):
            meta_lines.append(f"🚘 <b>Modello/Serie:</b> {html.escape(str(metadata['carrozzeria_generazione']))}")
        if metadata.get("anno_immatricolazione"):
            meta_lines.append(f"📅 <b>Anno:</b> {html.escape(str(metadata['anno_immatricolazione']))}")
        if metadata.get("optional_chiave"):
            opts = ", ".join(html.escape(str(o)) for o in metadata["optional_chiave"][:5])
            meta_lines.append(f"✨ <b>Optional rilevati:</b> {opts}")
        if metadata.get("stato_batteria_autonomia_km"):
            meta_lines.append(f"🔋 <b>Autonomia:</b> {html.escape(str(metadata['stato_batteria_autonomia_km']))}")
        if metadata.get("foto_urls"):
            meta_lines.append(f"📸 <b>Foto archiviate:</b> {len(metadata['foto_urls'])} foto HD (WebP)")

    # 2. Cucina & Scontrini
    elif category == "Cucina & Alimentazione":
        if metadata.get("supermercato"):
            meta_lines.append(f"🏪 <b>Supermercato:</b> {html.escape(str(metadata['supermercato']))}")
        if metadata.get("totale_spesa_eur"):
            try:
                tot_val = float(metadata['totale_spesa_eur'])
                meta_lines.append(f"🧾 <b>Totale spesa:</b> {tot_val:.2f} €")
            except Exception:
                meta_lines.append(f"🧾 <b>Totale spesa:</b> {html.escape(str(metadata['totale_spesa_eur']))} €")
        if metadata.get("data_scontrino"):
            meta_lines.append(f"📅 <b>Data scontrino:</b> {html.escape(str(metadata['data_scontrino']))}")
        if metadata.get("ingredienti_principali"):
            ings = ", ".join(html.escape(str(i)) for i in metadata["ingredienti_principali"])
            label = "🥗 <b>Alimenti in dispensa:</b>" if metadata.get("supermercato") else "🥗 <b>Ingredienti chiave:</b>"
            meta_lines.append(f"{label} {ings}")
        if metadata.get("alimenti_deperibili"):
            dep = ", ".join(html.escape(str(d)) for d in metadata["alimenti_deperibili"])
            meta_lines.append(f"⏳ <b>Freschi da consumare a breve:</b> {dep}")
        if metadata.get("tempo_stimato"):
            meta_lines.append(f"⏱️ <b>Tempo stimato:</b> {html.escape(str(metadata['tempo_stimato']))}")
        if metadata.get("stile"):
            meta_lines.append(f"🥑 <b>Stile:</b> {html.escape(str(metadata['stile']))}")
        if metadata.get("attrezzatura_richiesta"):
            meta_lines.append(f"🍳 <b>Cottura/Strumenti:</b> {html.escape(str(metadata['attrezzatura_richiesta']))}")

    # 3. Tech & AI
    elif category == "AI, Tech & Software":
        if metadata.get("nome_tool"):
            meta_lines.append(f"💻 <b>Tool/Modello:</b> {html.escape(str(metadata['nome_tool']))}")
        if metadata.get("funzione_primaria"):
            meta_lines.append(f"⚙️ <b>Funzione:</b> {html.escape(str(metadata['funzione_primaria']))}")
        if metadata.get("prezzo_tipo"):
            meta_lines.append(f"🏷️ <b>Prezzo/Licenza:</b> {html.escape(str(metadata['prezzo_tipo']))}")
        if metadata.get("casi_d_uso"):
            meta_lines.append(f"💡 <b>Casi d'uso:</b> {html.escape(str(metadata['casi_d_uso']))}")

    # 4. Notizie & Economia
    elif category == "Notizie, Attualità & Economia":
        if metadata.get("argomento"):
            meta_lines.append(f"🌍 <b>Argomento:</b> {html.escape(str(metadata['argomento']))}")
        if metadata.get("takeaway_principale"):
            meta_lines.append(f"💡 <b>Punto Chiave:</b> {html.escape(str(metadata['takeaway_principale']))}")
        if metadata.get("soggetti_chiave"):
            meta_lines.append(f"👥 <b>Soggetti:</b> {html.escape(str(metadata['soggetti_chiave']))}")

    # 5. Fitness & Sport
    elif category == "Fitness, Sport & Salute":
        if metadata.get("gruppo_muscolare"):
            meta_lines.append(f"💪 <b>Focus muscolare:</b> {html.escape(str(metadata['gruppo_muscolare']))}")
        if metadata.get("tipo_allenamento"):
            meta_lines.append(f"🏋️ <b>Tipo workout:</b> {html.escape(str(metadata['tipo_allenamento']))}")
        if metadata.get("errori_comuni_segnalati"):
            meta_lines.append(f"⚠️ <b>Attenzione a:</b> {html.escape(str(metadata['errori_comuni_segnalati']))}")

    # 6. Produttività & Finanza
    elif category == "Produttività, Finanza Personale & Business":
        if metadata.get("metodologia"):
            meta_lines.append(f"📈 <b>Metodologia:</b> {html.escape(str(metadata['metodologia']))}")
        if metadata.get("consiglio_azionabile"):
            meta_lines.append(f"🎯 <b>Azione pratica:</b> {html.escape(str(metadata['consiglio_azionabile']))}")

    # 7. Viaggi & Luoghi
    elif category == "Viaggi, Ristoranti & Luoghi":
        if metadata.get("citta_paese"):
            meta_lines.append(f"📍 <b>Destinazione:</b> {html.escape(str(metadata['citta_paese']))}")
        if metadata.get("tipo_luogo"):
            meta_lines.append(f"🏖️ <b>Tipologia:</b> {html.escape(str(metadata['tipo_luogo']))}")
        if metadata.get("prezzo_indicativo"):
            meta_lines.append(f"💶 <b>Fascia prezzo:</b> {html.escape(str(metadata['prezzo_indicativo']))}")

    # 8. Media
    elif category == "Media, Film, Libri & Podcast":
        if metadata.get("titolo_opera"):
            meta_lines.append(f"🎬 <b>Opera:</b> {html.escape(str(metadata['titolo_opera']))}")
        if metadata.get("genere"):
            meta_lines.append(f"🎭 <b>Genere:</b> {html.escape(str(metadata['genere']))}")
        if metadata.get("piattaforma"):
            meta_lines.append(f"📺 <b>Disponibile su:</b> {html.escape(str(metadata['piattaforma']))}")

    # 9. Life Hacks & Casa
    elif category == "Life Hacks, Casa & Fai da Te":
        if metadata.get("problema_risolto"):
            meta_lines.append(f"🛠️ <b>Risolve:</b> {html.escape(str(metadata['problema_risolto']))}")
        if metadata.get("strumenti_necessari"):
            meta_lines.append(f"🧰 <b>Occorrente:</b> {html.escape(str(metadata['strumenti_necessari']))}")

    # 10. Altro / Generico
    else:
        if metadata.get("tipo_contenuto"):
            meta_lines.append(f"📋 <b>Tipo:</b> {html.escape(str(metadata['tipo_contenuto']))}")
        if metadata.get("dettagli_chiave"):
            meta_lines.append(f"🔑 <b>Dettagli:</b> {html.escape(str(metadata['dettagli_chiave']))}")

    # Campi trasversali a tutte le categorie (Entità citate, Classifiche & Valutazioni)
    if metadata.get("entita_chiave"):
        entita_list = [html.escape(str(e)) for e in metadata["entita_chiave"] if str(e).strip()]
        if entita_list:
            preview = ", ".join(entita_list[:8])
            if len(entita_list) > 8:
                preview += f" ... (+{len(entita_list) - 8})"
            meta_lines.append(f"🎯 <b>Elementi citati ({len(entita_list)}):</b> {preview}")

    # Valutazioni, motivazioni e classifiche riga per riga
    classifica_val = _normalize_meta_field(metadata.get("classifica"))
    dettagli_val = _normalize_meta_field(metadata.get("dettagli_entita"))

    if classifica_val and dettagli_val:
        if classifica_val == dettagli_val:
            meta_lines.append(f"🏆 <b>Classifica & Motivazioni:</b>\n{html.escape(classifica_val)}")
        else:
            meta_lines.append(f"🏆 <b>Classifica / Tier:</b>\n{html.escape(classifica_val)}")
            meta_lines.append(f"📋 <b>Valutazioni & Motivazioni:</b>\n{html.escape(dettagli_val)}")
    elif classifica_val:
        meta_lines.append(f"🏆 <b>Classifica & Motivazioni:</b>\n{html.escape(classifica_val)}")
    elif dettagli_val:
        meta_lines.append(f"📋 <b>Valutazioni & Motivazioni:</b>\n{html.escape(dettagli_val)}")

    if meta_lines:
        lines.append("")
        lines.append("📊 <b>Informazioni Aggiunte:</b>")
        lines.extend(meta_lines)

    # Tags
    if tags:
        tag_str = " ".join(f"#{html.escape(str(t).replace('-', '_').replace(' ', '_'))}" for t in tags[:6])
        lines.append("")
        lines.append(f"🏷️ {tag_str}")

    # Fonte originale sicura
    if source_url:
        esc_url = html.escape(str(source_url), quote=True)
        lines.append("")
        lines.append(f'🔗 <a href="{esc_url}">Apri Link Originale</a>')

    if quality == "link_only":
        lines.append("")
        lines.append("💡 <i>Incolla qui il testo o i dettagli per arricchire questa scheda.</i>")

    return "\n".join(lines)


def format_learning_pill(item: Dict[str, Any]) -> str:
    """
    Formatta una pillola di apprendimento/ripasso concisa e azionabile per il comando /pillola.
    """
    title = item.get("title", "Pillola Formativa")
    category = item.get("category", "")
    summary = item.get("summary", "")
    metadata = item.get("metadata") or {}
    tags = item.get("tags") or []
    source_url = item.get("source_url")
    emoji = CATEGORY_EMOJIS.get(category, "💡")

    lines = [
        "🧠 <b>Pillola di Apprendimento & Ripasso</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"{emoji} <b>{html.escape(title)}</b>",
        f"📂 <i>{html.escape(category)}</i>",
        "",
    ]

    takeaway = (
        metadata.get("takeaway_principale")
        or metadata.get("consiglio_azionabile")
        or metadata.get("problema_risolto")
    )
    if takeaway:
        lines.append(f"🎯 <b>Takeaway:</b> {html.escape(str(takeaway))}\n")

    if summary:
        lines.append(f"📝 <b>Sintesi:</b> {html.escape(summary)}")

    dettagli = _normalize_meta_field(metadata.get("dettagli_entita") or metadata.get("classifica"))
    if dettagli:
        snippet = "\n".join(dettagli.split("\n")[:4])
        lines.append("")
        lines.append(f"🔑 <b>Punti Chiave:</b>\n{html.escape(snippet)}")

    if tags:
        tag_str = " ".join(f"#{html.escape(str(t).replace('-', '_').replace(' ', '_'))}" for t in tags[:5])
        lines.append("")
        lines.append(f"🏷️ {tag_str}")

    if source_url:
        lines.append("")
        lines.append(f'🔗 <a href="{html.escape(source_url, quote=True)}">Rivedi scheda originale</a>')

    lines.extend([
        "",
        "💡 <i>Tocca '🔄 Altra pillola' per ripassare un altro concetto salvato!</i>",
    ])

    return "\n".join(lines)


def build_pill_keyboard() -> InlineKeyboardMarkup:
    """Tastiera per il comando /pillola con tasto per estrarne un'altra."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Altra pillola", callback_data="next_pillola")]
    ])

