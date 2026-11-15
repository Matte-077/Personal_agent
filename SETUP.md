# 📋 Configuration & Credentials Guide | Guida alla Configurazione

> **Language / Lingua:**  
> 🇬🇧 **[English Version](#-english-version)** | 🇮🇹 **[Versione Italiana](#-versione-italiana)**

---

# 🇬🇧 English Version

A comprehensive step-by-step guide explaining where to find and how to configure all credentials to run the Personal AI Second Brain ("Segretario Totale") at **zero cloud cost**.

---

## 📌 Table of Contents (English)
1. [Core Essentials (Telegram + Google Gemini)](#1-core-essentials-telegram--gemini)
2. [Cloud Database: Supabase (Optional for Local SQLite)](#2-cloud-database-supabase)
3. [Instagram Burner Cookie (Optional)](#3-instagram-burner-cookie-optional)
4. [24/7 Cloud Hosting: Render (Optional for Local PC)](#4-247-cloud-hosting-render)
5. [Environment Variables Summary Table (`.env`)](#5-environment-variables-summary-table-env)

---

### 1. Core Essentials (Telegram + Gemini)

To start the agent (either locally or in the cloud), you only need **Telegram** and **Google Gemini**:

#### A. Telegram Bot Token & User ID Whitelist
The bot interacts **exclusively** with your allowed Telegram user account to protect your privacy and API quotas.

1. **Create the Telegram Bot:**
   * Open Telegram and search for [@BotFather](https://t.me/BotFather).
   * Send the command `/newbot`.
   * Choose a friendly name (e.g. `My Second Brain`) and a username ending in `bot` (e.g. `my_second_brain_bot`).
   * BotFather will reply with an API token like:
     `7123456789:AAHAbcDeFgHiJkLmNoPqRsTuVwXyZ`
   * Add it to `.env`:
     ```env
     TELEGRAM_BOT_TOKEN=7123456789:AAHAbcDeFgHiJkLmNoPqRsTuVwXyZ
     ```

2. **Find Your Telegram User ID:**
   * Search for [@userinfobot](https://t.me/userinfobot) (or [@raw_data_bot](https://t.me/raw_data_bot)) on Telegram.
   * Send any message: it will reply with your numerical **Id** (e.g. `123456789`).
   * Add it to `.env`:
     ```env
     ALLOWED_TELEGRAM_USER_IDS=123456789
     ```
   *(To whitelist multiple family members or devices, separate them with commas: `123456789,987654321`)*.

---

#### B. Google Gemini API Key (100% Free)
Powers multimodal analysis (videos, voice notes, grocery receipts, articles) and dense vector embeddings (768-dim).

1. Visit **[Google AI Studio](https://aistudio.google.com/app/apikey)** and sign in with your Google account.
2. Click **"Create API Key"** (or *"Get API key"*).
3. Select an existing Google Cloud project or create a new free one in 1 click.
4. Copy your key (starts with `AIzaSy...`).
5. Add it to `.env`:
   ```env
   GEMINI_API_KEY=AIzaSy_your_gemini_api_key
   ```

> [!TIP]
> **Want to test the agent immediately on your local PC without touching Supabase?**  
> Set in `.env`:
> ```env
> BOT_MODE=polling
> DB_PROVIDER=sqlite
> AI_PROVIDER=gemini
> ```
> And double-click `start_local.bat`. The agent will store everything locally in `data/agente.db`!

---

### 2. Cloud Database: Supabase
*(Required only if setting `DB_PROVIDER=supabase` for 24/7 cloud sync).*

1. **Create Project:**
   * Sign up for free at **[supabase.com](https://supabase.com)**.
   * Create a new project (e.g., `second-brain-db`).
   * Choose a strong database password and select region **Frankfurt (eu-central-1)** (recommended for minimal latency with Render).

2. **Retrieve API Keys:**
   * In the Supabase sidebar, go to **Project Settings** (gear icon) ➔ **API**.
   * Copy the **Project URL** (e.g. `https://xyzproject.supabase.co`).
   * Copy the **`service_role` (Secret)** key (starts with `sb_secret_...` or JWT).  
     *Security note:* We use the service_role key server-side to bypass RLS for HNSW vector searches; never share it publicly.
   * Add them to `.env`:
     ```env
     SUPABASE_URL=https://xyzproject.supabase.co
     SUPABASE_SECRET_KEY=sb_secret_your_secret_key
     ```

3. **Initialize Database Schema & RPC Functions (SQL Editor):**
   * In Supabase, open **SQL Editor**.
   * Open and execute the 5 migration files located in `migrations/` in chronological order:
     1. `migrations/001_init.sql` (Enables pgvector, creates `items` table, HNSW & FTS indices)
     2. `migrations/002_match_items.sql` (HNSW semantic vector search RPC function)
     3. `migrations/003_multiuser_url_constraint.sql` (Multi-user composite URL constraint)
     4. `migrations/004_search_automotive.sql` (Automotive numerical filter search RPC)
     5. `migrations/005_bilingual_search.sql` (Italian + English bilingual full-text search)

4. **Create Storage Bucket for Photos:**
   * In the Supabase sidebar, go to **Storage** ➔ **New bucket**.
   * Bucket name: `car-photos`.
   * Enable **"Public bucket"** (allows the bot and dashboard to display compressed WebP photos).
   * Click **Save**.

---

### 3. Instagram Burner Cookie (Optional)

> [!IMPORTANT]
> **If you forward videos directly in Telegram chat, NO COOKIE IS NEEDED!**  
> Multimodal OCR and audio transcription achieve 100% success rate without cookies.

Instagram cookies are only used when sharing raw links (`https://instagram.com/reel/...`) to bypass Meta's datacenter IP rate limits from Render.

#### How to extract `sessionid`:
1. **Security Rule:** Always use a **secondary burner account**, never your personal account!
2. Open Chrome or Firefox and log into [instagram.com](https://instagram.com) with the burner account.
3. Press `F12` to open Developer Tools.
4. Go to **Application** (Chrome) or **Storage** (Firefox) tab.
5. In the left panel, expand **Cookies** ➔ click `https://www.instagram.com`.
6. Locate the cookie named **`sessionid`** and copy its alphanumeric value.
7. Add it to `.env`:
   ```env
   IG_SESSIONID=6829104%3Ayour_session_id
   ```

---

### 4. 24/7 Cloud Hosting: Render
*(For running the bot 24/7 in the cloud when your PC is turned off).*

1. Sign up on **[render.com](https://render.com)** with your GitHub account.
2. Click **New +** ➔ **Web Service**.
3. Select your GitHub repository `Agente_personale`.
4. Basic configuration:
   * **Name:** `agente-personale`
   * **Region:** `Frankfurt (EU Central)`
   * **Runtime:** `Python` (or `Docker` using the included Dockerfile)
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
   * **Instance Type:** `Free` (512 MB RAM)
5. **Environment Variables:**
   Under **Environment**, add the keys from your `.env`:
   * `BOT_MODE` = `webhook`
   * `ENVIRONMENT` = `production`
   * `WEBHOOK_URL` = `https://agente-personale.onrender.com` (assigned by Render)
   * `TELEGRAM_BOT_TOKEN` = `...`
   * `ALLOWED_TELEGRAM_USER_IDS` = `...`
   * `TELEGRAM_WEBHOOK_SECRET` = `random_alphanumeric_secret`
   * `GEMINI_API_KEY` = `...`
   * `SUPABASE_URL` = `...`
   * `SUPABASE_SECRET_KEY` = `...`
6. **Free Keep-Alive Ping (Prevent Cold Starts):**
   * Render Free Tier sleeps after 15 minutes of inactivity.
   * Create a free account on **[Cron-Job.org](https://cron-job.org)** or **[UptimeRobot](https://uptimerobot.com)**.
   * Add a recurring HTTP GET ping every 10 minutes to:
     `https://your-service.onrender.com/healthz`
   * This maintains the server and Telegram webhook active 24/7!

---

### 5. Environment Variables Summary Table (`.env`)

| Variable | Required? | Source / Purpose |
| :--- | :---: | :--- |
| `TELEGRAM_BOT_TOKEN` | **YES** | [@BotFather](https://t.me/BotFather) on Telegram. |
| `ALLOWED_TELEGRAM_USER_IDS` | **YES** | Your numerical user ID from [@userinfobot](https://t.me/userinfobot). |
| `GEMINI_API_KEY` | **YES** (if Cloud AI) | [Google AI Studio](https://aistudio.google.com/app/apikey) (Free). |
| `BOT_MODE` | **YES** | `polling` (local PC behind NAT) or `webhook` (cloud Render). |
| `DB_PROVIDER` | **YES** | `sqlite` (local autonomous) or `supabase` (cloud Postgres). |
| `SUPABASE_URL` | If Supabase | Supabase Dashboard ➔ Project Settings ➔ API. |
| `SUPABASE_SECRET_KEY` | If Supabase | Supabase Dashboard ➔ Project Settings ➔ API (`service_role`). |
| `WEBHOOK_URL` | If Webhook | HTTPS public URL provided by Render. |
| `TELEGRAM_WEBHOOK_SECRET` | If Webhook | Random secret string verifying Telegram webhook requests. |
| `IG_SESSIONID` | *Optional* | Burner Instagram session cookie for datacenter IP bypass. |
| `RAPIDAPI_KEY` | *Optional* | Free-tier fallback bridge for Instagram scraper API. |
| `JINA_API_KEY` | *Optional* | Increases rate limits for the anti-bot web reader `r.jina.ai`. |

---
---

# 🇮🇹 Versione Italiana

Una guida completa passo-passo che spiega dove trovare e come inserire **tutte le credenziali necessarie** per far funzionare l'Agente Personale al 100% gratuitamente.

---

## 📌 Indice dei Contenuti (Italiano)
1. [I due elementi minimi indispensabili (Telegram + Gemini)](#1-i-due-elementi-minimi-indispensabili-per-iniziare-it)
2. [Database Cloud Supabase (Opzionale se usi SQLite locale)](#2-database-cloud-supabase-it)
3. [Cookie Instagram Burner (Opzionale)](#3-cookie-instagram-burner-opzionale-it)
4. [Deploy Cloud 24/7 su Render (Opzionale se usi il PC locale)](#4-deploy-cloud-247-su-render-it)
5. [Tabella Riassuntiva delle Variabili d'Ambiente (`.env`)](#5-tabella-riassuntiva-delle-variabili-denv-it)

---

### 1. I Due Elementi Minimi Indispensabili per Iniziare {#1-i-due-elementi-minimi-indispensabili-per-iniziare-it}

Per avviare l'agente (sia in locale che in cloud), ti servono solo **Telegram** e **Google Gemini**:

#### A. Telegram Bot Token & ID Utente (Whitelist)
Il bot risponde **esclusivamente** al tuo account Telegram per proteggere privacy e quote API.

1. **Creare il Bot:**
   * Apri Telegram e cerca [@BotFather](https://t.me/BotFather).
   * Invia il comando `/newbot`.
   * Scegli un nome (es. `Mio Segretario`) e uno username che finisca con `bot` (es. `mio_segretario_personale_bot`).
   * BotFather ti risponderà con un token del tipo:
     `7123456789:AAHAbcDeFgHiJkLmNoPqRsTuVwXyZ`
   * Inseriscilo in `.env`:
     ```env
     TELEGRAM_BOT_TOKEN=7123456789:AAHAbcDeFgHiJkLmNoPqRsTuVwXyZ
     ```

2. **Trovare il tuo ID Utente Telegram:**
   * Cerca su Telegram [@userinfobot](https://t.me/userinfobot) (oppure [@raw_data_bot](https://t.me/raw_data_bot)).
   * Avvialo o invia un qualsiasi messaggio: ti risponderà mostrandoti il tuo **Id** numerico (es. `123456789`).
   * Inseriscilo in `.env`:
     ```env
     ALLOWED_TELEGRAM_USER_IDS=123456789
     ```
   *(Se vuoi autorizzare più persone, separa gli ID con virgole: `123456789,987654321`)*.

---

#### B. Google Gemini API Key (100% Gratuita)
Usata per l'analisi multimodale (video, audio, scontrini, testo) e per la generazione di embedding vettoriali.

1. Vai su **[Google AI Studio](https://aistudio.google.com/app/apikey)** ed effettua il login con il tuo account Google.
2. Clicca sul pulsante **"Create API Key"** (o *"Get API key"*).
3. Seleziona un progetto Google Cloud (o creane uno nuovo gratuito in un clic).
4. Copia la chiave generata (inizia con `AIzaSy...`).
5. Inseriscila in `.env`:
   ```env
   GEMINI_API_KEY=AIzaSy_tua_chiave_gemini
   ```

> [!TIP]
> **Vuoi testare il bot subito in locale senza toccare Supabase?**  
> Imposta in `.env`:
> ```env
> BOT_MODE=polling
> DB_PROVIDER=sqlite
> AI_PROVIDER=gemini
> ```
> E fai doppio clic su `start_local.bat`. Il bot salverà tutto nel file locale `data/agente.db`!

---

### 2. Database Cloud Supabase {#2-database-cloud-supabase-it}
*(Necessario solo se imposti `DB_PROVIDER=supabase` per avere l'archivio accessibile 24/7 dal cloud).*

1. **Creare il Progetto:**
   * Registrati gratuitamente su **[supabase.com](https://supabase.com)**.
   * Crea una nuova organizzazione e un nuovo progetto (es. `segretario-db`).
   * Scegli una password per il database e seleziona la regione **Frankfurt (eu-central-1)** (ideale per la vicinanza ai server Render).

2. **Recuperare le Chiavi API:**
   * Nella dashboard di Supabase, vai in basso a sinistra su **Project Settings** (icona ingranaggio) ➔ **API**.
   * Copia **Project URL** (es. `https://xyzproject.supabase.co`).
   * Copia la chiave **`service_role` (Secret)** (formato moderno `sb_secret_...` o JWT).  
     *Nota di sicurezza:* Usiamo la service role key lato server per bypassare le RLS ed eseguire ricerche vettoriali; non esporla mai pubblicamente.
   * Inseriscile in `.env`:
     ```env
     SUPABASE_URL=https://xyzproject.supabase.co
     SUPABASE_SECRET_KEY=sb_secret_tua_chiave_segreta
     ```

3. **Inizializzare le Tabelle e le Funzioni Vettoriali (SQL Editor):**
   * Nel menu laterale di Supabase, apri **SQL Editor**.
   * Apri i file presenti nella cartella `migrations/` ed eseguili **uno alla volta in ordine**:
     1. `migrations/001_init.sql` (Attiva pgvector, crea tabella `items`, indici HNSW e full-text)
     2. `migrations/002_match_items.sql` (Crea la funzione RPC per la ricerca semantica vettoriale)
     3. `migrations/003_multiuser_url_constraint.sql` (Vincolo univoco URL per utente)
     4. `migrations/004_search_automotive.sql` (Funzione RPC filtri numerici auto)
     5. `migrations/005_bilingual_search.sql` (Ricerca full-text bilingue IT/EN)

4. **Creare il Bucket per le Foto Auto:**
   * Nel menu laterale, vai su **Storage** ➔ **New bucket**.
   * Nome bucket: `car-photos`.
   * Spunta **"Public bucket"** (consente al bot e alla dashboard di mostrare le foto compresse in WebP).
   * Clicca **Save**.

---

### 3. Cookie Instagram Burner (Opzionale) {#3-cookie-instagram-burner-opzionale-it}

> [!IMPORTANT]
> **Se inoltri direttamente il video in chat o invii il file multimediale, NON SERVE ALCUN COOKIE!**  
> L'analisi video e audio funziona al 100% senza cookie.

I cookie di Instagram servono **esclusivamente** se vuoi che il bot scarichi automaticamente i video quando invii un semplice link testuale (`https://instagram.com/reel/...`) dai server di Render, poiché Meta applica controlli anti-bot sui datacenter.

#### Come estrarre il cookie `sessionid`:
1. **Regola fondamentale di sicurezza:** Usa **sempre un account secondario o burner**, mai il tuo account personale!
2. Apri Chrome o Firefox in modalità normale o anonima e accedi a [instagram.com](https://instagram.com) con l'account burner.
3. Premi `F12` sulla tastiera per aprire gli **Strumenti per Sviluppatori**.
4. Vai nella scheda **Application** (su Chrome) o **Storage** (su Firefox).
5. Nel menu a sinistra espandi **Cookies** ➔ clicca su `https://www.instagram.com`.
6. Cerca il cookie denominato **`sessionid`** e copia il suo valore alfanumerico (es. `6829104%3A...`).
7. Inseriscilo in `.env`:
   ```env
   IG_SESSIONID=6829104%3Atuo_session_id
   ```

---

### 4. Deploy Cloud 24/7 su Render {#4-deploy-cloud-247-su-render-it}
*(Per avere il bot sempre attivo online anche a PC spento).*

1. Registrati su **[render.com](https://render.com)** con il tuo account GitHub.
2. Clicca su **New +** ➔ **Web Service**.
3. Seleziona il tuo repository GitHub `Agente_personale`.
4. Configurazione base:
   * **Name:** `agente-personale`
   * **Region:** `Frankfurt (EU Central)`
   * **Runtime:** `Python` (o `Docker` se preferisci compilare tramite il Dockerfile incluso)
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
   * **Instance Type:** `Free` (512 MB RAM)
5. **Environment Variables:**
   Clicca su **Environment** e aggiungi le variabili configurate nel tuo `.env`:
   * `BOT_MODE` = `webhook`
   * `ENVIRONMENT` = `production`
   * `WEBHOOK_URL` = `https://agente-personale.onrender.com` (l'indirizzo assegnato da Render)
   * `TELEGRAM_BOT_TOKEN` = `...`
   * `ALLOWED_TELEGRAM_USER_IDS` = `...`
   * `TELEGRAM_WEBHOOK_SECRET` = `qualsiasi_stringa_segreta_alfanumerica`
   * `GEMINI_API_KEY` = `...`
   * `SUPABASE_URL` = `...`
   * `SUPABASE_SECRET_KEY` = `...`
   * *(Opzionale)* `IG_SESSIONID` = `...`
6. **Keep-Alive Gratuito (Anti Cold-Start):**
   * Il Free Tier di Render va in sospensione dopo 15 minuti di inattività.
   * Crea un account gratuito su **[Cron-Job.org](https://cron-job.org)** o **[UptimeRobot](https://uptimerobot.com)**.
   * Aggiungi un monitor HTTP GET ogni 10 minuti verso:
     `https://tuo-servizio.onrender.com/healthz`
   * In questo modo il servizio rimarrà sempre reattivo 24 ore su 24 senza alcun ritardo di accensione!

---

### 5. Tabella Riassuntiva delle Variabili d'Ambiente (`.env`) {#5-tabella-riassuntiva-delle-variabili-denv-it}

| Variabile | Obbligatoria? | Dove reperirla / Note |
| :--- | :---: | :--- |
| `TELEGRAM_BOT_TOKEN` | **SÌ** | [@BotFather](https://t.me/BotFather) su Telegram. |
| `ALLOWED_TELEGRAM_USER_IDS` | **SÌ** | Il tuo ID numerico da [@userinfobot](https://t.me/userinfobot). |
| `GEMINI_API_KEY` | **SÌ** (se Cloud AI) | [Google AI Studio](https://aistudio.google.com/app/apikey) (gratis). |
| `BOT_MODE` | **SÌ** | `polling` (per PC locale) o `webhook` (per Render cloud). |
| `DB_PROVIDER` | **SÌ** | `sqlite` (locale autonomo) o `supabase` (cloud Postgres). |
| `SUPABASE_URL` | Se Supabase | Dashboard Supabase ➔ Project Settings ➔ API. |
| `SUPABASE_SECRET_KEY` | Se Supabase | Dashboard Supabase ➔ Project Settings ➔ API (`service_role`). |
| `WEBHOOK_URL` | Se Webhook | Indirizzo pubblico HTTPS assegnato da Render. |
| `TELEGRAM_WEBHOOK_SECRET` | Se Webhook | Stringa casuale per autenticare i webhook da Telegram. |
| `IG_SESSIONID` | *Opzionale* | Cookie sessione da account Instagram burner (F12). |
| `RAPIDAPI_KEY` | *Opzionale* | Per fallback su RapidAPI Instagram Scraper (free tier). |
| `JINA_API_KEY` | *Opzionale* | Per aumentare la quota del reader antibot r.jina.ai. |
