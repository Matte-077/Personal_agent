from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class CategoryEnum(str, Enum):
    AUTOMOTIVE = "Automotive & Annunci Auto"
    CUCINA = "Cucina & Alimentazione"
    TECH = "AI, Tech & Software"
    NEWS = "Notizie, Attualità & Economia"
    FITNESS = "Fitness, Sport & Salute"
    BUSINESS = "Produttività, Finanza Personale & Business"
    TRAVEL = "Viaggi, Ristoranti & Luoghi"
    MEDIA = "Media, Film, Libri & Podcast"
    LIFE_HACKS = "Life Hacks, Casa & Fai da Te"
    ALTRO = "Altro / Varie & Non Classificato"


class ItemMetadata(BaseModel):
    # --- 1. Automotive & Annunci Auto ---
    marca: Optional[str] = Field(default=None, description="Marca del veicolo (es. BMW, Audi)")
    modello: Optional[str] = Field(default=None, description="Modello (es. 330e, M3, Golf)")
    carrozzeria_generazione: Optional[str] = Field(default=None, description="Es. G20 (Berlina), G21 (Touring), SUV")
    motorizzazione: Optional[str] = Field(default=None, description="Es. Ibrida Plug-in PHEV, Benzina, Diesel")
    trazione: Optional[str] = Field(default=None, description="Es. RWD (Posteriore), xDrive, AWD")
    anno_immatricolazione: Optional[int] = Field(default=None, description="Anno immatricolazione (es. 2021)")
    chilometraggio_km: Optional[int] = Field(default=None, description="Chilometri come intero (es. 58000)")
    prezzo_eur: Optional[int] = Field(default=None, description="Prezzo in euro come intero senza simboli (es. 34900)")
    paese_venditore: Optional[str] = Field(default=None, description="Es. Germania (DE), Italia (IT)")
    allestimento: Optional[str] = Field(default=None, description="Es. M Sport, Luxury Line, Advantage")
    optional_chiave: Optional[List[str]] = Field(default_factory=list, description="Optional chiave (es. Fari Laser, Head-up Display, Gancio traino, Tetto panoramico)")
    stato_batteria_autonomia_km: Optional[str] = Field(default=None, description="Autonomia elettrica dichiarata o reale")
    note_affidabilita_o_difetti: Optional[str] = Field(default=None, description="Note affidabilità o difetti noti")

    # --- 2. Cucina & Alimentazione ---
    ingredienti_principali: Optional[List[str]] = Field(default_factory=list, description="Ingredienti principali normalizzati in LOWERCASE (es. ['latte', 'uova', 'cioccolato'])")
    tempo_stimato: Optional[str] = Field(default=None, description="veloce (<15 min), medio (30-60 min), lungo")
    tipo_pasto: Optional[str] = Field(default=None, description="colazione, pranzo, cena, snack, dessert")
    stile: Optional[str] = Field(default=None, description="proteico, light, vegetariano, comfort food")
    attrezzatura_richiesta: Optional[str] = Field(default=None, description="forno, padella, friggitrice ad aria, microonde")
    supermercato: Optional[str] = Field(default=None, description="Insegna o supermercato dello scontrino (es. Esselunga, Lidl, Coop, Conad)")
    totale_spesa_eur: Optional[float] = Field(default=None, description="Importo totale scontrino spesa in euro")
    data_scontrino: Optional[str] = Field(default=None, description="Data emissione scontrino YYYY-MM-DD")
    alimenti_deperibili: Optional[List[str]] = Field(default_factory=list, description="Alimenti deperibili da consumare a breve (carne fresca, pesce, latticini, verdure fresche)")

    # --- 3. AI, Tech & Software ---
    nome_tool: Optional[str] = Field(default=None, description="Nome del software o modello AI (es. Cursor, Kling 1.5)")
    funzione_primaria: Optional[str] = Field(default=None, description="video generation, coding, voice cloning, agenti")
    prezzo_tipo: Optional[str] = Field(default=None, description="free, freemium, open-source, subscription")
    casi_d_uso: Optional[str] = Field(default=None, description="Esempi pratici di utilizzo")
    prompt_o_link: Optional[str] = Field(default=None, description="Prompt menzionati o repository GitHub")

    # --- 4. Notizie, Attualità & Economia ---
    argomento: Optional[str] = Field(default=None, description="geopolitica, finanza, mercati, scienza, innovazione")
    takeaway_principale: Optional[str] = Field(default=None, description="2-3 frasi con i concetti cardine")
    soggetti_chiave: Optional[str] = Field(default=None, description="Persone o aziende menzionate")

    # --- 5. Fitness, Sport & Salute ---
    gruppo_muscolare: Optional[str] = Field(default=None, description="gambe, schiena, petto, core, total body")
    tipo_allenamento: Optional[str] = Field(default=None, description="pesi, calisthenics, mobilità/stretching, cardio")
    errori_comuni_segnalati: Optional[str] = Field(default=None, description="Note sulla corretta esecuzione")

    # --- 6. Produttività, Finanza Personale & Business ---
    metodologia: Optional[str] = Field(default=None, description="Time blocking, PAC, Regola 50/30/20")
    consiglio_azionabile: Optional[str] = Field(default=None, description="Azione immediata da mettere in pratica")

    # --- 7. Viaggi, Ristoranti & Luoghi ---
    citta_paese: Optional[str] = Field(default=None, description="Città o luogo geografico")
    tipo_luogo: Optional[str] = Field(default=None, description="ristorante, hotel, trekking, locale")
    prezzo_indicativo: Optional[str] = Field(default=None, description="economico, medio, alto")

    # --- 8. Media, Film, Libri & Podcast ---
    titolo_opera: Optional[str] = Field(default=None, description="Titolo opera")
    genere: Optional[str] = Field(default=None, description="Genere di appartenenza")
    piattaforma: Optional[str] = Field(default=None, description="Netflix, Spotify, Kindle, cartaceo")

    # --- 9. Life Hacks, Casa & Fai da Te ---
    problema_risolto: Optional[str] = Field(default=None, description="Cosa risolve il trucco/hack")
    strumenti_necessari: Optional[str] = Field(default=None, description="Cosa serve per realizzarlo")

    # --- 10. Altro / Generico ---
    tipo_contenuto: Optional[str] = Field(default=None, description="nota, documento, contatto, link generico")
    dettagli_chiave: Optional[str] = Field(default=None, description="Punti salienti o note libere")
    note_aggiuntive: Optional[str] = Field(default=None, description="Contesto utile o note integrative")
    foto_urls: Optional[List[str]] = Field(default=None, description="URL pubblici delle foto archiviate su Storage")
    link_annuncio: Optional[str] = Field(default=None, description="Link all'annuncio o risorsa se presente")

    # --- Campi trasversali (Elenchi, Certificazioni, Confronti, Classifiche) ---
    entita_chiave: Optional[List[str]] = Field(
        default_factory=list,
        description="Lista di tutti i nomi esatti di entità, tool, certificazioni, corsi, modelli auto, locali o opere citati (es. ['AWS Certified AI Practitioner', 'Google Data Analytics', 'Stanford Machine Learning'])",
    )
    dettagli_entita: Optional[str] = Field(
        default=None,
        description="Dettagli puntuali per ciascuna entità formattati riga per riga: • [Tier/Valutazione] Nome — Motivazione esatta | Pro: ... | Contro: ... | Esame: ...",
    )
    classifica: Optional[str] = Field(
        default=None,
        description="Classifica o Tier List con voto e motivazione esatta per ciascuna voce (vietate righe di soli nomi)",
    )

    @field_validator("ingredienti_principali", mode="after")
    @classmethod
    def normalize_ingredients_lowercase(cls, v: Optional[List[str]]) -> List[str]:
        if not v:
            return []
        return [item.strip().lower() for item in v if item and item.strip()]


class ItemClassification(BaseModel):
    """
    Schema JSON strutturato restituito da Gemini per ogni elemento salvato.
    """
    category: CategoryEnum = Field(description="Una delle 10 categorie tassonomiche prestabilite")
    subcategory: str = Field(description="Sottocategoria descrittiva (es. Annuncio Vendita, Ricetta Veloce, Modello AI, Certificazioni & Carriera)")
    title: str = Field(description="Titolo chiaro, sintetico e descrittivo")
    summary: str = Field(description="Sintesi elegante e completa in 2-4 frasi in lingua italiana")
    language: str = Field(default="it", description="Codice lingua primaria rilevata (default: it)")
    confidence: float = Field(ge=0.0, le=1.0, description="Punteggio confidenza della classificazione tra 0.00 e 1.00")
    tags: List[str] = Field(default_factory=list, description="Lista di 4-8 tag brevi in lowercase, senza hashtag")
    embedding_text: str = Field(
        description="Testo semantico denso e ricco per la vettorizzazione (include titolo, categoria, entità chiave, dettagli tecnici e parole chiave di ricerca)"
    )
    metadata: ItemMetadata = Field(
        default_factory=ItemMetadata,
        description="Metadati strutturati specifici per la categoria selezionata"
    )


SYSTEM_PROMPT = """Sei l'assistente AI analitico per l'Agente Personale 'Segretario Totale'.
Il tuo compito è analizzare il contenuto ricevuto (testo di note, trascrizioni vocali, articoli web o didascalie di reel) e catalogarlo con la massima precisione.

REGOLE FONDAMENTALI:
1. Scegli rigorosamente UNA sola categoria tra le 10 disponibili in `category`. Se il contenuto è ambiguo o non rientra chiaramente nelle prime 9, usa 'Altro / Varie & Non Classificato' con una confidence appropriata.
2. CERTIFICAZIONI FORMATIVE & CARRIERA: Tutte le certificazioni professionali, corsi per arricchire il curriculum, attestati di formazione e percorsi di upskilling (anche se a tema AI, Cloud, Dati o Software) DEVONO essere categorizzati sotto 'Produttività, Finanza Personale & Business' (con sottocategoria es. 'Certificazioni & Carriera' o 'Formazione Professionale'), poiché la loro finalità per l'utente è la propria crescita professionale e curricolare. La categoria 'AI, Tech & Software' è riservata a tool, librerie, modelli, estensioni o automazioni usate come strumenti tecnici.
3. REGOLA ANTI-GENERALIZZAZIONE & FORMATO MOTIVAZIONI VINCOLANTE:
   Quando il contenuto menziona, elenca o confronta più elementi (es. certificazioni con Tier List, 10 corsi, confronto tool, auto):
   - È SEVERAMENTE VIETATO usare formule vaghe come 'varie certificazioni', 'alcuni corsi' o elenchi di soli nomi senza motivazione (es. VIETATO scrivere semplicemente 'Tier S: Corso A, Corso B').
   - In `metadata.entita_chiave`: inserisci TUTTI i nomi propri esatti citati nel contenuto (es. ['AWS Certified AI Practitioner', 'Google Data Analytics', 'Stanford Machine Learning']).
   - In `metadata.classifica` e/o `metadata.dettagli_entita`: usa OBBLIGATORIAMENTE il formato a elenco puntato riga per riga:
     • [Tier/Voto] Nome Entità — Motivazione esatta del creator | Pro: ... | Contro: ... | Esame: ...
     DEVI riportare per ciascuna voce il giudizio critico dell'autore e il PERCHÉ ha assegnato quel livello (es. '• [Tier S] Stanford Machine Learning — Brand accademico più prestigioso e riconosciuto | Pro: massimo valore CV | Esame: compiti graduati').
   - Includi tutti i nomi delle entità anche in `embedding_text` e nei `tags` affinché siano reperibili sia via ricerca semantica vettoriale che Full-Text.
4. Per 'Automotive & Annunci Auto': estrai con estrema precisione marca, modello, carrozzeria/generazione (es. G20 o G21 per BMW Serie 3), prezzo intero in euro (`prezzo_eur`), chilometri interi (`chilometraggio_km`) e tutti gli optional chiave (specialmente Fari Laser, Head-up Display, Gancio traino, Tetto).
5. Per 'Cucina & Alimentazione': normalizza SEMPRE gli ingredienti principali in minuscolo (es. 'uova', 'farina', 'latte') per consentire ricerche esatte e abbinamenti con le offerte.
6. SCONTRINI E SPESE (Cucina & Dispensa): Se il contenuto è uno scontrino della spesa (o ricevuta di supermercato/alimentari), assegna SEMPRE categoria 'Cucina & Alimentazione' e sottocategoria 'Scontrino Spesa / Dispensa'. In `metadata.ingredienti_principali` inserisci la lista di tutti gli alimenti acquistati normalizzati in minuscolo (es. ['latte', 'ricotta', 'spinaci', 'uova', 'pollo']). Se rilevati, compila `supermercato`, `totale_spesa_eur`, `data_scontrino` e `alimenti_deperibili`.
7. Per 'embedding_text': crea una stringa semantica ricca che contenga tutti i termini cruciali per la ricerca vettoriale (es. per certificazioni: 'certificazioni AI curriculum AWS Certified AI Practitioner Google Data Analytics Stanford Andrew Ng Tier S A valore lavoro proctored').
8. Rispondi sempre in lingua italiana, curando la forma del titolo e del sommario.
"""
