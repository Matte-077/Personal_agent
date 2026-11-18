# Personal AI Second Brain ("Segretario Totale")

[![Running Cost](https://img.shields.io/badge/Running_Cost-$0.00%20%2F%20100%25%20Free%20Tier-2ea44f?style=for-the-badge&logo=shieldsdotio&logoColor=white)](SETUP.md)

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

[![Supabase](https://img.shields.io/badge/Supabase-pgvector_%26_Storage-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)

[![Google Gemini](https://img.shields.io/badge/Google_Gemini-3.1_Flash_Lite-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)

[![Telegram Bot](https://img.shields.io/badge/Telegram_Bot-Async_API_%26_Mini_App-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)

[![Built with Antigravity](https://img.shields.io/badge/Built_with-Antigravity_IDE-7928CA?style=for-the-badge&logo=googlecloud&logoColor=white)](https://antigravity.google)

An autonomous 24/7 AI-powered personal assistant and digital second brain that ingests videos, articles, receipts, and voice notes directly through Telegram, complete with a dark-mode web dashboard.

> [!IMPORTANT]
> ### 💸 100% Free to Run — Zero Cloud Costs (.00 / month)
> This project is engineered specifically to operate **100% free of charge**, fitting comfortably within the **permanent, generous free tiers of every service used** — **no credit card required, zero subscriptions, and zero hidden fees**:
> - **Google Gemini 3.1 Flash Lite:** Permanent free tier with **15 requests/min and 1,500 requests/day** for multimodal video/audio analysis and dense 768-dim vector embeddings (personal usage typically requires ~20–50 requests/day, leaving over 95% of the free quota untouched).
> - **Render Free Web Service:** **750 free instance hours per month** (a full month has 720–744 hours), granting 24/7 continuous cloud operation kept awake with an automated free 10-minute heartbeat ping.
> - **Supabase Cloud Database:** **Free 500 MB PostgreSQL database + 1 GB file storage** with native pgvector included (easily accommodates tens of thousands of cards, metadata, and compressed WebP photos).
> - **Telegram Bot Platform:** **100% free with unlimited messages**, instant webhook delivery, and zero platform fees.
> - **Edge-TTS Neural Voice:** Microsoft Edge neural speech synthesis with **zero API keys and zero cost**.
> - **Local Mode (SQLite + Ollama):** Runs **100% offline and free** on your own PC, mini-PC, or Raspberry Pi with zero cloud dependencies.

---

## 🏗️ Architecture Overview

```

[ Smartphone (Instagram / TikTok / YouTube / mobile.de / Voice / Receipts) ]

                                      │

                                      ▼ (Direct Share or Audio / Photo)

                        [ Telegram Bot Gateway ] (100% Free)

                                      │

          ┌───────────────────────────┴───────────────────────────┐

          ▼ (Cloud: Webhook 24/7 - $0.00/mo)                      ▼ (Local PC: Long-Polling - $0.00/mo)

[ Render Free Web Service ]                             [ Local PC / Mini PC / Home Server ]

  - Free Tier (750 free hrs/mo = 24/7)                    - Zero router configuration required

  - Always active via 10-min heartbeat                    - Catch-Up on Boot (Buffered messages processed)

  - Cloud WebApp (/app)                                   - Local SQLite Database (data/agente.db)

  - Supabase Database (Free 500 MB + pgvector)            - In-memory vector search (<85ms)

          │                                                       │

          └───────────────────────────┬───────────────────────────┘

                                      ▼

                       [ Google Gemini Flash Lite AI ]

                        - 100% Free Tier (1,500 requests/day)

                        - Multimodal Video & Voice Analysis

                        - Structured Knowledge & Vector Search

```

---

## ✨ Key Features & Capabilities

### 🔍 1. Smart Hybrid Search & Bilingual Consultation

- **Meaning + Keyword Search:** Understands concepts (*"quick dinner ideas"*, *"reliable hybrid cars"*) while matching exact terms, technical codes, and model names.

- **Language Mirroring:** Ask in Italian or English—the agent automatically replies in the same language, seamlessly summarizing saved content regardless of its original language.

- **Numerical & Relational Filtering:** Query numerical thresholds naturally (e.g., *"cars under 35,000 € with laser lights"* or *"recipes under 20 minutes"*).

### 📱 2. Telegram Mini App & Web Dashboard (`/app`)

- **Visual Workspace:** Clean dark-mode dashboard to browse, search, and filter your entire knowledge base on mobile or desktop.

- **Side-by-Side Comparison:** Compare vehicles (price, mileage, specs, import costs), recipes, or tech tools in an interactive modal.

- **Zero-Password Secure Access:** Instant one-tap access directly inside Telegram, or secure 48-hour access links for desktop browsers.

### 📥 3. Universal Media & Content Ingestion

- **Social Videos (Instagram Reels, TikTok, YouTube Shorts):** Ingests links or forwarded videos, automatically extracting transcripts, key entities, pros/cons, and tier rankings using multimodal AI.

- **Web & News Articles:** Automatically extracts clean article text, bypassing anti-bot shields and reading paywall-free summaries.

- **Photos & Voice Notes:** Ingests voice memos and images directly from Telegram chats.

### 🚗 4. Automotive Market & German Import Calculator

- **Listing Extraction:** Ingests vehicle listings (mobile.de and portals), saving price, mileage, year, engine, trim, key options, and compressed photos.

- **German Import Estimation:** Calculates real on-the-road Italian costs for imported cars, including carrier transport, nationalization, agency registration fees, and license plates.

- **Tax & Hybrid Savings:** Automatically checks for plug-in hybrid tax discounts and Italian Superbollo exemptions.

### 🍳 5. Smart Pantry & Empty-the-Fridge Cooking

- **Receipt Scanning:** Send photos of supermarket receipts to automatically extract totals, store names, and perishable foods.

- **Empty-the-Fridge Suggestions:** Ask what to cook based on what you have at home.

- **Interactive Checklist:** Generate an interactive Telegram shopping list from any saved recipe, highlighting missing ingredients.

- **Smart Flyer Deals & Basket Savings (Roadmap):** Automatically scrapes weekly flyers from major local supermarkets to find the best deals for ingredients required by saved recipe reels and your recurring staple shopping list.

### 🎙️ 6. Voice Assistant & Daily Flashcards

- **Voice In ➔ Voice Out:** Send a Telegram voice message; the bot listens, consults your database, and replies with both text and a natural voice note.

- **Spaced Micro-Learning (`/pillola`):** Rotating interactive flashcards with practical tips from your saved tech, productivity, and cooking notes.

### 💻 7. Dual-Mode: Cloud 24/7 or 100% Local PC

- **Cloud 24/7 (Webhook):** Runs around the clock on Render's free tier with automated keep-alive, ready to ingest content anytime.

- **Local PC (Long-Polling):** Run locally on any PC, laptop, or Raspberry Pi behind standard home Wi-Fi without opening router ports.

- **Catch-Up on Boot:** When your PC is off, Telegram safely queues messages. Upon booting, the bot processes the entire backlog in order.

- **100% Offline Database:** Optional local SQLite database with fast vector search and local Ollama AI support for total privacy.

### 💸 8. 100% Zero Running Cost & Privacy by Design

The entire architecture is strictly engineered to **operate completely free of charge by fitting 100% within the permanent free-tier limits of all services used**:

| Service / Component | Free Tier Allowance | Personal Assistant Daily Usage | Monthly Cost |

| :--- | :--- | :--- | :--- |

| **Google Gemini Flash Lite** | 1,500 requests/day & 15 RPM | ~20–50 requests/day | **0.00 € / $0.00** |

| **Render Web Service** | 750 free hours/month | 720–744 hours/month (24/7 continuous) | **0.00 € / $0.00** |

| **Supabase (PostgreSQL + pgvector)** | 500 MB DB & 1 GB Storage | ~20–50 MB for thousands of cards | **0.00 € / $0.00** |

| **UptimeRobot / Cron-Job.org** | 50 free monitors / unlimited pings | 1 HTTP ping every 10 min | **0.00 € / $0.00** |

| **Telegram Bot Platform** | Unlimited messages & WebApp hosting | Single personal whitelist | **0.00 € / $0.00** |

| **Edge-TTS Neural Voice** | Unlimited public synthesis | On-demand voice notes | **0.00 € / $0.00** |

| **Local Mode (SQLite + Ollama)** | Self-hosted on your machine | 100% offline & autonomous | **0.00 € / $0.00** |

- **No Credit Card Required:** You can set up the entire stack using free accounts across Google AI Studio, Render, and Supabase without ever entering payment information.

- **Strict User Whitelist:** Only Telegram user IDs listed in `ALLOWED_TELEGRAM_USER_IDS` are permitted to interact with the bot; unauthorized requests are rejected immediately to protect your privacy and API quotas.

---

## 💬 Bot Commands & Interactions

### Commands

| Command | Aliases | Description |

|---|---|---|

| `/start`, `/help` | - | Overview, capabilities guide, and quick examples |

| `/dashboard` | `/app` | Opens the Telegram Mini App or generates a 48h signed Desktop Web link |

| `/pillola` | `/impara`, `/ripasso` | Spaced repetition flashcard from saved tips & notes |

| `/elimina <keyword>` | `/cancella` | Searches and soft-deletes cards with a confirmation prompt |

### Instant Ingestion (Just send it to the chat)

- 🔗 **Links:** Send any URL (Instagram Reels, TikTok, YouTube Shorts, mobile.de listings, articles) to automatically transcribe, analyze, and save it.

- 🎙️ **Voice Notes:** Ask questions aloud or record notes; the bot replies with rich text and natural voice.

- 🧾 **Photos & Receipts:** Send supermarket receipts to extract totals and perishable food items.

---

## 🚀 Getting Started

Everything you need to configure and run the bot is documented step-by-step in **[SETUP.md](SETUP.md)** (available in both **English** and **Italian**).

> [!NOTE]
> **No credit card or paid subscription is required for any step.** All accounts (Google AI Studio, Render, Supabase, Telegram) can be created with permanent 100% free plans that more than cover daily personal assistant usage.

### Option A: Local PC (Windows 1-Click)

1. Copy `.env.example` to `.env` and add your keys (see **[SETUP.md](SETUP.md)**).

2. Double-click **`start_local.bat`**.

The launcher automatically sets up Python, installs dependencies, catches up on any pending Telegram messages, and opens the visual dashboard (`http://localhost:8000/app`).

### Option B: Cloud 24/7 (Render Free Tier)

1. Connect this repository to a **Render Web Service** (Python runtime).

2. Set Build Command: `pip install -r requirements.txt`

3. Set Start Command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`

4. Add your environment variables in the Render dashboard and set up a 10-minute heartbeat ping to `/healthz` (details in **[SETUP.md](SETUP.md)**).

---

## 📄 License & Documentation

- Check **[SETUP.md](SETUP.md)** for the complete credentials guide and installation tutorial (bilingual EN/IT).

- Check **[GEMINI.md](file:///c:/Users/matte/Desktop/PROGETTI/Agente_personale/GEMINI.md)** for architecture specifications and safety rules.

- Distributed under the MIT License.

