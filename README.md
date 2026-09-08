# 🛡️ Punjab Police AI-Powered Drug Intelligence System

An end-to-end intelligence gathering and anti-detection forensic platform engineered for **Punjab Police** to combat drug trafficking (Chitta/Heroin, Opium, Tramadol) across **Surface Web**, **Dark Web (.onion)**, and **Encrypted Messaging (Telegram)**.

---

## 🏛️ System Architecture

```
                               ┌──────────────────────────────────────────────┐
                               │       PUNJAB POLICE INVESTIGATOR UI          │
                               │   React 18 + Tailwind CSS + Cytoscape.js    │
                               └──────────────────────┬───────────────────────┘
                                                      │ REST + WebSockets
                               ┌──────────────────────▼───────────────────────┐
                               │           FastAPI ASYNC BACKEND              │
                               │     JWT / RBAC Auth & SHA-256 Evidence       │
                               └──┬──────────────────┬──────────────────────┬─┘
                                  │                  │                      │
        ┌─────────────────────────▼─────┐ ┌──────────▼──────────────┐ ┌─────▼──────────────────────────┐
        │     1. SURFACE WEB PIPELINE   │ │  2. DARK WEB PIPELINE   │ │  3. ENCRYPTED MESSAGING (TG)   │
        │ • Playwright Stealth          │ │ • Tor SOCKS5h Routing   │ │ • Telethon MTProto API         │
        │ • Bot-challenge / WAF Evasion │ │ • Stem Circuit Rotation │ │ • Public Preview Fallback      │
        │ • IP Proxy Pool Rotation      │ │ • v3 .onion Crawler     │ │ • Channel Auto-Discovery       │
        │ • Recursive Link Crawler      │ │ • DNS-Leak Prevention   │ │ • Tesseract OCR for Photos     │
        └───────────────────────────────┘ └─────────────────────────┘ └────────────────────────────────┘
```

---

## 🚀 Quickstart Guide

### 1. Backend (FastAPI + Async Python)

```bash
cd backend

# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Install Playwright Chromium stealth browser
playwright install chromium

# 3. Start the FastAPI server
uvicorn app:app --reload --port 8000
```
- **Backend API Base**: `http://127.0.0.1:8000`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`
- **First run**: the application generates an administrator password and prints
  it **once** to the console. Sign in with username `admin_punjab` and that
  password, then change it immediately - the account is blocked from other use
  until you do. No credential is stored in this repository.

### Before first start

```bash
cd backend
python scripts/generate_secrets.py   # writes backend/.env with real signing keys
```

The application refuses to start on the placeholder secrets unless `DEBUG=True`.

---

### 2. Frontend (React 18 + Tailwind + Cytoscape)

```bash
cd frontend

# 1. Install packages
npm install

# 2. Launch Vite development server
npm run dev
```
- **Investigator Dashboard**: `http://localhost:5173`

---

## 🔑 Key Features Implemented

1. **Anti-Bot & Anti-Detection Evasion Engine**:
   - Randomizes Canvas/WebGL fingerprints, realistic User-Agents, and browser viewports.
   - Dynamic delays & jitter (2s–7s) to eliminate rhythmic automated scraping patterns.
   - Proactive CAPTCHA / Cloudflare / WAF challenge page detection.

2. **IP Proxy Rotation Pool**:
   - Supports HTTP, HTTPS, and SOCKS5 proxies.
   - Round-robin and randomized rotation strategies with latency and health tracking.
   - Auto-removes dead proxies after consecutive connection timeouts.

3. **Dark Web (.onion) Ingestion**:
   - Routes traffic via Tor SOCKS5 proxy (`socks5h://`) with zero DNS leaks.
   - Signals Tor controller (`Signal.NEWNYM`) to rotate circuits and exit nodes.
   - Regex-based v3 56-character `.onion` link extraction crawler.

4. **Encrypted Messaging Ingestion (Telegram)**:
   - Dual-engine: Official Telethon MTProto client with resilient public web preview fallback (`t.me/s/...`).
   - Cross-linked group and channel discovery feedback loop.

5. **Trafficking Network Analysis (Cytoscape.js + Neo4j schema)**:
   - Interactive visual graph connecting Suspects, Telegram Channels, Onion Marketplaces, Drug Products, and Crypto Wallets.
   - Zoom, drag, node inspection, and layout algorithms (COSE, Breadthfirst).

6. **Blockchain Forensics (Bitcoin & Ethereum)**:
   - Queries Blockstream Esplora API for BTC addresses harvested from dark web listings.
   - Inspects confirmed on-chain transaction hashes, balances, and transaction volume.

7. **Tamper-Evident Chain of Custody & PDF Dossier Export**:
   - Computes SHA-256 cryptographic hashes for every scraped snippet for Section 65B Indian Evidence Act court admissibility.
   - Generates official intelligence dossiers with officer badge verification.
   - Immutable audit logging of all investigator actions.
