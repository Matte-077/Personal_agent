# GEMINI.md - Project: Personal AI Second Brain ("Segretario Totale")

> [!CAUTION]
> ## 🛡️ SAFETY PROTOCOL & MANDATORY CONFIRMATION RULES
> 1. **No Unauthorized Modifications on Supabase:** Before executing any DDL or DML write/modification operation (`CREATE`, `ALTER`, `DROP`, `UPDATE`, `DELETE`, `TRUNCATE`) on the Supabase database, the agent MUST stop, display the exact query/action, and await explicit user confirmation. *Note:* Read-only queries (`SELECT`) for inspection are always permitted without prior confirmation.
> 2. **No Destructive Actions on Render:** Before creating services, modifying environment variables, triggering manual restarts, or deleting services on Render, the agent MUST describe the action and request explicit user consent.
> 3. **Protection of Credentials & Telegram Whitelist:**
>    - No secret token (`SUPABASE_SECRET_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `RENDER_API_KEY`, `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`) must ever be hardcoded or committed to git. Always use the `.env` file (enforced in `.gitignore`).
>    - **Bot Access Whitelist:** The bot accepts commands and ingests content exclusively for Telegram accounts specified in `ALLOWED_TELEGRAM_USER_IDS`. Any request from unauthorized users must be immediately rejected and ignored to protect user privacy and API quotas.

---

## 1. Project Vision
**Personal AI Second Brain ("Segretario Totale")** is a cloud-native, 24/7 intelligent personal assistant running at zero cloud cost, designed to streamline daily life and act as an external second brain.

### Core Objectives:
1. **Instant Smartphone Ingestion:** Ingest any content (Instagram Reels, vehicle listings like mobile.de, web articles, voice notes, photos/receipts) via direct sharing to a private Telegram bot protected by a strict user ID whitelist.
2. **Automatic Understanding & Taxonomy:** Analyze incoming content using the **Google Gemini 3.1 Flash Lite API** (generous free quota, ideal for instantaneous multimodal processing at zero cost) and parameterized dense vector embeddings.
3. **Structured & Vector Database:** Dual storage architecture:
   - **Cloud Mode:** **Supabase (PostgreSQL + pgvector + Full-Text Search)** for relational queries (numerical filters, prices, mileage, ingredients) and semantic search ("AI video ideas", "buying advice").
   - **Local Mode:** **SQLite + FTS5** with in-memory Python vector cosine similarity (<85ms) and local WebP disk storage.
4. **Proactive Consultative Agent:** Answer daily questions by cross-referencing saved items (e.g., *"I have eggs and milk in the fridge, what can I cook quickly?"*, *"Show me the best BMW 330e saved under 35,000 € with laser lights"*).
5. **Continuous Evolution:** Periodic vehicle price tracking, weekly summaries, receipt OCR for dynamic pantry management, supermarket flyer deal scraping cross-referenced with saved recipe ingredients and fixed staple lists, and controlled external service integrations.

---

## 2. Technical Architecture (Dual-Mode: Cloud 24/7 & Local PC Catch-Up)

The system supports two interchangeable operating modes via `BOT_MODE`:
1. **Cloud Mode (`BOT_MODE=webhook`):** Active 24/7 on Render at zero cost, ideal for continuous immediate ingestion.
2. **Local Mode (`BOT_MODE=polling`):** Ideal for running on a personal PC, home server, mini-PC, or Raspberry Pi. Requires zero open router ports, dynamic DNS, or public IP (operates behind NAT/Firewall) and sequentially downloads all backlog messages sent while the PC was turned off (*Catch-Up on Boot*).

```
[ Smartphone (Instagram / TikTok / YouTube / mobile.de / News / Voice / Receipts) ]
                                      │
                                      ▼
                      [ Telegram Bot Cloud Gateway ]
                                      │
          ┌───────────────────────────┴────────────────────────────┐
          ▼ (Cloud Mode: Webhook HTTPS)                            ▼ (Local Mode: Long-Polling)
[ Render Free Web Service (FastAPI 24/7) ]               [ Local PC / Mini PC / Home Server ]
  - 10-min Keep-Alive Ping (UptimeRobot)                   - Zero open ports (behind NAT/Firewall)
  - Telegram Webhook Listener                              - Catch-Up on Boot (Backlog processed)
  - Cloud WebApp Dashboard (/app)                          - Local Dashboard (http://localhost:8000/app)
          │                                                        │
          ├───────────────────────────┬────────────────────────────┤
          ▼                           ▼                            ▼
[ Ingestion Pipeline ]       [ AI Engine Dual ]           [ Database Dual Provider ]
 - Universal yt-dlp           - Cloud: Gemini Flash Lite   - Cloud: Supabase (Postgres + pgvector)
 - trafilatura + Jina Reader  - Local: Ollama Offline     - Local: SQLite FTS5 + Python Vectors
 - Multi-tier Instagram       - 768-dim Embeddings         - WebP Photo Storage (Cloud / Disk)
```

### Technology Stack:
* **Language & Runtime:** Python 3.11+, Asyncio.
* **User Interface:** Private Telegram Bot (`python-telegram-bot`) secured with numerical user ID allowlist.
* **Intelligence & Multimodality:** `google-genai` with configurable model `GEMINI_MODEL` (default: `gemini-3.1-flash-lite`, fallback `gemini-2.5-flash-lite`) and configurable embeddings `GEMINI_EMBEDDING_MODEL` (`gemini-embedding-001`, 768 float dimensions).
* **Database & Vectors:**
  - **Cloud:** **Supabase Free Tier** (PostgreSQL 15+ with `pgvector` HNSW index + bilingual Italian/English Full-Text Search + `car-photos` storage bucket for WebP images). Server-side authentication via `SUPABASE_SECRET_KEY` (modern `sb_secret_...` format) with seamless fallback to `SUPABASE_SERVICE_ROLE_KEY`.
  - **Local:** **SQLite 3** (`data/agente.db`) with PRAGMA WAL, FTS5 virtual tables, automatic synchronization triggers, and in-memory cosine vector similarity.
* **Hosting & Keep-Alive:** **Render** (Free Web Service). Prevent cold-starts (sleep after 15 minutes of inactivity causing Telegram webhook timeouts) via automated 10-minute HTTP ping to `/healthz` using free external cron services (Cron-Job.org / UptimeRobot).
* **Asynchronous Execution & Resource Safeguards:** Heavy AI inference, image compression, and DB writes dispatched to worker threads via `asyncio.to_thread` with strict timeouts (25s–40s) to keep FastAPI's event-loop non-blocking. Strict 20 MB guard on Telegram media to protect the container's 512 MB RAM limit.

---

### Multi-Tier Pipeline for Instagram Reels & Video Content:
The bot implements a cascaded fallback strategy to maximize extraction success and eliminate datacenter IP blocks:
0. **Tier 0 - Native Media / Direct Forward (100% Success Rate):** If the message contains an uploaded video/audio file or is a native Telegram forward with media, the bot bypasses all web scraping and sends the stream directly to Gemini Multimodal.
1. **Tier 1 - Optimized `yt-dlp` (with optional session burner cookies):** When a link is shared, extracts metadata and retrieves the direct MP4 stream URL. If configured (`INSTAGRAM_COOKIES` or `IG_SESSIONID` from a secondary burner account, never personal), session cookies are injected via temporary `cookiefile` to bypass datacenter IP blocks; expired cookies automatically trigger an alert.
2. **Tier 2 - OpenGraph Metadata Scraper:** Rapid extraction of public HTML metadata (preview image, title, and public caption) via OpenGraph tags without requiring login.
3. **Tier 3 - API Gateway / Media Bridge (RapidAPI + Cobalt):** Automated fallback to external bridges: RapidAPI Instagram Scraper (free tier if `RAPIDAPI_KEY` configured), followed by public Cobalt bridge instances for MP4 stream retrieval.
4. **Tier 4 - Asynchronous Retry Queue:** If Meta triggers a temporary rate-limit, the bot retries at short intervals.
5. **Tier 5 - Transparent Assisted Fallback:** If all automatic tiers fail (e.g. banned datacenter IP or private account), the bot informs the user cleanly without crashing:
   > *"Meta blocked automatic extraction for this reel. To save it anyway, paste the caption here or forward the video/audio file directly to this chat."*
6. **Automated Gemini Multimodal Analysis:**
   - **From Native Media (Tier 0):** Direct stream sent to Gemini Flash Lite with the 4-section prompt (Faithful Transcription, Named Entities, Entity Details, Rankings/Tier Lists).
   - **From Link (Tier 1/3):** If `media_url` is recovered, downloads the MP4 stream in memory with a 20 MB safety guard and queries Gemini for on-screen OCR and 4-section voice transcription. Falls back cleanly to text caption if video exceeds 20 MB.

### Multi-Tier Pipeline for Web Articles & News Portals:
Online news portals (e.g. tech publications) frequently deploy anti-bot defenses (Cloudflare Turnstile, Varnish WAF) returning 429/403 errors to cloud datacenter IPs. The web pipeline implements a 3-tier cascade:
1. **Tier 1 - Direct Download (`httpx` + `trafilatura`):** Ultra-fast clean text extraction with active bot-challenge detection (`is_bot_challenge`).
2. **Tier 2 - Reader Bridge (`r.jina.ai`):** If direct download encounters 429, 403, WAF, or Turnstile challenges, automatically queries the Jina reader bridge JSON API for clean markdown text and title.
3. **Tier 3 - Semantic Slug Fallback (`extract_slug_title`):** If completely blocked, extracts the title and semantic topic from the URL slug (e.g. `"xiaomi-smart-light..."` $\rightarrow$ *"Xiaomi smart light..."*), preventing "Error" cards from ever entering the database.

---

## 3. Database Taxonomy & Category Schemas

Every ingested item is parsed by Gemini into a card with common fields (`id`, `category`, `title`, `summary`, `tags`, `source_url`, `created_at`) plus **category-specific structured metadata**:

### 🚗 1. Automotive & Vehicle Listings (Focus BMW 330e G20/G21 & mobile.de)
* **Purpose:** Market tracking, saving listings from mobile.de and portals, reliability reviews, and purchase advice.
* **Metadata Schema:**
  * `marca`: string (e.g. *BMW*)
  * `modello`: string (e.g. *330e*)
  * `carrozzeria_generazione`: string (*G20 (Sedan)* or *G21 (Touring)*)
  * `motorizzazione`: string (*Plug-in Hybrid PHEV - B48 2.0L + Electric Motor, 292 hp*)
  * `trazione`: string (*RWD (Rear-wheel)* or *xDrive (AWD)*)
  * `anno_immatricolazione`: integer (e.g. *2020, 2021 (pre-LCI) or 2022+ (LCI restyling)*)
  * `chilometraggio_km`: integer (e.g. *58000*)
  * `prezzo_eur`: integer (listing price)
  * `paese_venditore`: string (*Germania (DE)*, *Italia (IT)*)
  * `allestimento`: string (*M Sport, Advantage, Luxury Line*)
  * `optional_chiave`: list of strings (e.g. *["Fari Laser", "Tetto Panoramico", "Head-up Display (HUD)", "Harman Kardon", "Driving Assistant Professional", "Gancio traino"]*)
  * `stato_batteria_autonomia_km`: electric range (e.g. *40-50 km*)
  * `note_affidabilita_o_difetti`: known model defects or recall notes.

---

### 🍳 2. Cooking & Nutrition
* **Purpose:** Empty-the-fridge recipes, saved social cooking videos, quick dinner ideas.
* **Metadata Schema:**
  * `ingredienti_principali`: normalized list of strings (e.g. *["eggs", "milk", "parmesan"]*)
  * `tempo_stimato`: string (*fast (<15 min), medium (30-60 min), long*)
  * `tipo_pasto`: string (*breakfast, lunch, dinner, snack, dessert*)
  * `stile`: string (*high-protein, light, vegetarian, comfort food*)
  * `attrezzatura_richiesta`: string (*skillet, oven, air fryer, microwave*)

---

### 🤖 3. AI, Tech & Software
* **Purpose:** Model releases (video, image, LLMs), developer tools, automation scripts.
* **Metadata Schema:**
  * `nome_tool`: string (e.g. *Cursor, Claude 3.5 Sonnet, Kling 1.5*)
  * `funzione_primaria`: string (*coding, video generation, agents, productivity*)
  * `prezzo_tipo`: string (*free, freemium, open-source, subscription*)
  * `casi_d_uso`: string (practical examples)
  * `prompt_o_link`: string (referenced prompts or GitHub repositories)

---

### 📰 4. News, Economics & Current Affairs
* **Purpose:** In-depth articles, macroeconomic trends, geopolitical analysis.
* **Metadata Schema:**
  * `argomento`: string (*geopolitics, markets, tech, science*)
  * `takeaway_principale`: string (2-3 concise bullet points)
  * `soggetti_chiave`: list of companies or key figures mentioned.

---

### 🏋️ 5. Fitness, Sport & Health
* **Purpose:** Workout routines, mobility exercises, posture corrections.
* **Metadata Schema:**
  * `gruppo_muscolare`: string (*legs, back, chest, core, full body*)
  * `tipo_allenamento`: string (*weights, calisthenics, stretching, cardio*)
  * `errori_comuni_segnalati`: string (form and safety notes)

---

### 💼 6. Productivity, Personal Finance & Career
* **Purpose:** Organization methods, investing habits, professional certifications and career upskilling.
* **Metadata Schema:**
  * `metodologia`: string (e.g. *Time blocking, DCA, 50/30/20 rule, Resume Tier List*)
  * `consiglio_azionabile`: string (immediate action step)

---

### 🌐 Cross-Category Universal Metadata (Rankings, Comparisons, Tier Lists)
* `entita_chiave`: list of exact names mentioned (e.g. `["AWS Certified AI Practitioner", "Stanford Machine Learning"]`).
* `dettagli_entita`: structured pros, cons, costs, proctored vs non-proctored verification.
* `classifica`: rankings or Tier Lists (e.g. *Tier S, Tier A, Tier B, Tier D*).

---

### ✈️ 7. Travel, Restaurants & Places
* **Metadata:** `citta_paese`, `tipo_luogo` (*restaurant, hotel, viewpoint*), `prezzo_indicativo`.

### 🎬 8. Media, Movies, Books & Podcasts
* **Metadata:** `titolo`, `genere`, `piattaforma` (*Netflix, Spotify, Kindle, paper*).

### 💡 9. Life Hacks, Home & DIY
* **Metadata:** `problema_risolto`, `strumenti_necessari`.

### 📦 10. Miscellaneous & Unclassified
* **Metadata:** `tipo_contenuto`, `dettagli_chiave`, `note_aggiuntive`.

---

## 4. Database Schema (Supabase PostgreSQL & SQLite)

### PostgreSQL (Supabase DDL):
```sql
-- Vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Primary items table
CREATE TABLE items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT DEFAULT 'default' NOT NULL,
    status TEXT DEFAULT 'active' NOT NULL,   -- 'active', 'archived', 'deleted'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    source_url TEXT,
    source_type TEXT NOT NULL CHECK (source_type IN (
        'instagram', 'mobile_de', 'web_article', 'text_note', 'voice', 'receipt', 'image', 'other'
    )),
    raw_text TEXT,
    category TEXT NOT NULL,
    subcategory TEXT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}'::jsonb,
    confidence NUMERIC(3,2) DEFAULT 1.00 CHECK (confidence >= 0.00 AND confidence <= 1.00),
    embedding VECTOR(768),
    search_tsv TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('italian', coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(raw_text,''))
    ) STORED,
    CONSTRAINT items_user_id_source_url_key UNIQUE (user_id, source_url)
);

-- Relational & JSONB indices
CREATE INDEX idx_items_category ON items(category);
CREATE INDEX idx_items_tags ON items USING GIN(tags);
CREATE INDEX idx_items_metadata ON items USING GIN(metadata);

-- HNSW Vector Index (Cosine distance)
CREATE INDEX idx_items_embedding ON items USING hnsw (embedding vector_cosine_ops);

-- Full-Text Search GIN index
CREATE INDEX idx_items_search ON items USING GIN(search_tsv);
```

---

## 5. Structured JSON Output from Gemini Flash Lite

When processing incoming text or multimodal media, Gemini produces structured JSON:

```json
{
  "category": "Automotive & Annunci Auto",
  "subcategory": "Annuncio Vendita",
  "title": "BMW 330e Touring M Sport (G21) - 2021",
  "summary": "German listing with 58,000 km, full M Sport trim, Laser headlights, HUD and tow hitch.",
  "language": "it",
  "confidence": 0.98,
  "tags": ["bmw", "330e", "g21", "touring", "m-sport", "laser", "mobile-de"],
  "embedding_text": "BMW 330e Touring M Sport G21 2021 plug-in hybrid laser headlights HUD tow hitch Germany 58000 km",
  "metadata": {
    "marca": "BMW",
    "modello": "330e",
    "carrozzeria_generazione": "G21 (Touring)",
    "anno_immatricolazione": 2021,
    "chilometraggio_km": 58000,
    "prezzo_eur": 34900,
    "paese_venditore": "Germania (DE)",
    "allestimento": "M Sport",
    "trazione": "RWD",
    "optional_chiave": ["Fari Laser", "Head-up Display", "Gancio traino", "Sedili riscaldabili"],
    "link_annuncio": "https://suchen.mobile.de/fahrzeuge/details.html?id=...",
    "extraction": {
      "tier": "direct",
      "quality": "full",
      "http_status": 200
    }
  }
}
```

---

## 6. Querying & Agent Consultation Modes

The bot automatically distinguishes between **saving** content and **answering questions**:

* **Saving Ingestion (URLs or descriptive notes):**
  $\rightarrow$ Executes extraction pipeline, categorizes with Gemini, computes dense 768-dim embedding, stores in database, and replies with structured Telegram card + inline actions.

* **Consultation Queries:**
  * **Rule 1: Bilingual & Language Mirroring:**
    The agent dynamically recognizes query language (Italian or English) and responds fluently in the **same language**, translating and synthesizing stored items regardless of their original language.
  * **Rule 2: Reciprocal Rank Fusion (RRF):**
    Combines sparse lexical search (exact acronyms: *B48, G21, HUD, Laser*) with dense vector similarity:
    $$RRF(d) = \sum_{m} \frac{1}{60 + \text{rank}_m(d)}$$
  * **Rule 3: Contextual Fridge & Pantry Heuristics:**
    Cross-references recent receipts and perishable foods with saved recipes to suggest empty-the-fridge meals.
  * **Rule 4: Automotive Financial Precision:**
    Uses PostgreSQL and Python numeric casting (e.g. `price <= 35000`) rather than lexicographical string comparisons.

---

## 7. Development Tooling & Project Structure

```
Agente_personale/
├── .env.example              # Documented environment variables template
├── .gitignore                # Strict exclusion for secrets, .env, *.db, and media
├── start_local.bat           # 1-Click Windows desktop launcher (Root entry point)
├── Dockerfile                # Render container runtime (Python 3.11-slim)
├── GEMINI.md                 # Primary architecture blueprint & safety rules
├── LICENSE                   # MIT License
├── README.md                 # Public repository presentation & quickstart
├── requirements.txt          # Python dependencies (mandatory for Render/pip)
├── SETUP.md                  # Bilingual step-by-step credentials tutorial (EN/IT)
├── migrations/               # PostgreSQL schema & RPC migrations (001 to 005)
└── src/                      # Complete application source code
    ├── config.py             # Pydantic Settings & dual-mode dispatcher
    ├── local_runner.py       # Master CLI local runner (polling, ASCII banner)
    ├── main.py               # FastAPI lifespan, endpoints (/app, /healthz, /webhook)
    ├── advisor/              # Consultative engine (RRF, Language Mirroring, TCO)
    ├── ai/                   # Gemini & Ollama clients, prompts
    ├── bot/                  # Telegram handlers, responses, cryptographic auth
    ├── db/                   # Supabase & SQLite clients, storage
    ├── extractors/           # Instagram, mobile.de, video, web extractors
    ├── static/               # Tailwind CSS Single Page App (/app dashboard)
    └── utils/                # Edge-TTS speech synthesis, WebP compression
```

---

## 8. Implementation Roadmap & Project Evolution

1. **Phase 1: Core Foundation & Resilience (COMPLETED)**
   - Supabase schema, pgvector, HNSW & FTS indices, RLS policies.
   - FastAPI on Render with keep-alive and Telegram whitelist.
   - Gemini Flash Lite client + 768-dim embeddings.
   - Multi-tier Instagram and mobile.de scrapers with WebP compression.

2. **Phase 2: Universal Ingestion & Automotive TCO (COMPLETED)**
   - YouTube Shorts & TikTok 4-section multimodal transcription.
   - German import TCO calculator (bisarca, plates, IPT, PHEV superbollo exemption).

3. **Phase 3: Dynamic Pantry & Receipt OCR (COMPLETED)**
   - Receipt OCR extracting store, total, and perishable items.
   - Interactive Telegram `[🛒 Crea Lista Spesa]` checklist.

4. **Phase 4: Hands-Free Voice Assistant & Micro-Learning (COMPLETED)**
   - Neural voice-in ➔ voice-out with `edge-tts` (`it-IT-DiegoNeural`).
   - Spaced repetition flashcards with `/pillola`.

5. **Phase 5: Telegram Mini App & Bilingual RRF Search (COMPLETED)**
   - Reciprocal Rank Fusion combining pgvector and Full-Text Search.
   - Bilingual Italian/English stemming with dynamic Language Mirroring.
   - Dark-mode Telegram Mini App & Web PWA (`/app`) with side-by-side comparison modal.

6. **Phase 22: Local Autonomous Bifurcation & Catch-Up on Boot (COMPLETED)**
   - Dual-Mode architecture: Cloud (Render Webhook) vs Local (Long-Polling behind NAT).
   - Local SQLite database (`data/agente.db`) with FTS5 and in-memory cosine vector similarity.
   - Local AI integration with Ollama (`llama3.2`, `nomic-embed-text`).
   - Catch-Up on Boot sequential backlog processing (`drop_pending_updates=False`).
   - 1-click launcher (`start_local.bat`).

7. **Phase 23: Extended Verification & Live E2E Battery (COMPLETED)**
   - Full live verification with Gemini 3.1 Flash Lite API, Edge-TTS, and bilingual Advisor.
   - 130 tests passing with 100% success rate (116 unit + 14 live, 0 errors).

8. **Phase 24: Smart Flyer Scraper & Recipe-Driven Grocery Deals (PLANNED / FUTURE)**
   - **Local Supermarket Flyer Ingestion:** Periodic crawler/fetcher targeting weekly promotional flyers of major regional supermarket chains (e.g. Esselunga, Coop, Conad, Lidl, Eurospin) via public aggregator feeds or direct retailer portals.
   - **Dual-Source Need Matching:**
     1. *Dynamic Recipe Stream:* Ingredients automatically extracted from cooking videos (Instagram Reels, TikTok, YouTube Shorts) saved in the `Cucina & Alimentazione` category.
     2. *Fixed Staple List:* User-defined list of recurring household essentials and pantry staples (e.g., extra virgin olive oil, coffee, Greek yogurt, chicken breast, oats, detergent).
   - **Intelligent Semantic Discount Matching:**
     - Uses Gemini Flash Lite and dense embeddings to map promotional flyer items (e.g., *"Petto di pollo a fette -30% a 7.99 €/kg"*) to recipe ingredients and staple items.
     - Basket cost comparison algorithm calculating which nearby supermarket yields the highest overall savings.
   - **Telegram Proactive Alerts & Interactive Route:**
     - Automated weekly digest (e.g. Friday morning before weekend grocery shopping) highlighting top discounts matching saved recipes.
     - On-demand query: *"What's on sale for my saved pasta recipes this week?"* or `/volantini`.
     - Interactive checklist: 1-tap item checkboxes grouped by store, showing original vs. discounted price.
