# Personal AI Second Brain ("Segretario Totale")

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Supabase](https://img.shields.io/badge/Supabase-pgvector_%26_Storage-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)
[![Google Gemini](https://img.shields.io/badge/Google_Gemini-3.1_Flash_Lite-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![Telegram Bot](https://img.shields.io/badge/Telegram_Bot-Async_API_%26_Mini_App-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Built with Antigravity](https://img.shields.io/badge/Built_with-Antigravity_IDE-7928CA?style=for-the-badge&logo=googlecloud&logoColor=white)](https://antigravity.google)

A 24/7 AI-powered personal assistant and second brain that ingests videos, articles, receipts, and voice notes directly through Telegram, featuring a visual web dashboard and running at zero cloud cost.

---

## 🏗️ Architecture Overview

```
[ Smartphone (Instagram / TikTok / YouTube / mobile.de / Voice / Receipts) ]
                                      │
                                      ▼ (Direct Share or Audio / Photo)
                       [ Telegram Bot Gateway ]
                                      │
          ┌───────────────────────────┴───────────────────────────┐
          ▼ (Cloud: Webhook 24/7)                                 ▼ (Local PC: Long-Polling behind NAT)
[ Render Free Web Service ]                             [ Local PC / Mini PC / Home Server ]
  - Always active via 10-min heartbeat                    - Zero router configuration required
  - Cloud WebApp (/app)                                   - Catch-Up on Boot (Buffered messages processed)
  - Supabase Database (PostgreSQL)                        - Local SQLite Database (data/agente.db)
          │                                                       │
          └───────────────────────────┬───────────────────────────┘
                                      ▼
                      [ Google Gemini Flash Lite AI ]
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

### 🔒 8. Privacy & Zero Cost
- **Strict User Whitelist:** Only Telegram user IDs listed in your configuration can access the bot; unauthorized users are ignored.
- **Zero Cloud Cost:** Engineered to run 100% within free cloud tiers (Google Gemini, Supabase, Render).

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
