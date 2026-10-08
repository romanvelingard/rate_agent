# Crypto Rate Agent ⚡

A high-frequency cryptocurrency exchange rate monitoring and analytics agent built with **FastAPI**, **SQLite WAL**, **CCXT**, and real-time **WebSockets**.

---

## 🌟 Key Features

1. **Sub-Second Check Frequency (0.5s)**:
   - High-speed rate checking every 500ms (0.5s) across multiple cryptocurrency pairs simultaneously.

2. **Separated Configuration (`config.yaml`)**:
   - Easily configure target exchange (`binance`, `coinbase`, `bybit`, `okx`, `kucoin`), list of tracked crypto pairs, update interval, retention windows, and chart rendering style (`candlestick` vs `line`).

3. **Dual-Tier Data Storage & Auto-Retention**:
   - **Tier 1 (Raw 0.5s Ticks)**: Retained for **7 days** (~1.15 GB disk space for 10 coins).
   - **Tier 2 (Aggregated 1-Minute Candles)**: Retained for **90 days** for statistical model training and 85% confidence trend predictions (~15 MB for 10 coins).
   - **Automated Hourly Purge**: SQLite WAL engine background task purges expired raw ticks automatically.

4. **Real-Time Interactive Dashboard**:
   - Modern glassmorphism UI streaming 0.5s updates over WebSockets.
   - Built with TradingView **Lightweight-Charts** library.
   - Includes real-time indicators ($EMA_{20}$, $EMA_{50}$, $RSI_{14}$) and natural language tendency signals with confidence scoring (50% – 92%).

---

## 🚀 Quick Start Guide

### 1. Virtual Environment & Requirements
The project uses `.venv` virtual environment created with Python 3.13+:

```bash
# Activate virtual environment (Windows)
.\.venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 2. Configuration (`config.yaml`)

Edit [config.yaml](file:///c:/Users/RomanVelingard/projects/rate_agent/config.yaml) to customize your exchange, currency pairs, and chart mode:

```yaml
exchange: "binance"          # Exchange choice
update_interval_ms: 500      # 0.5s checking interval

currencies:
  - "BTC/USDT"
  - "ETH/USDT"
  - "SOL/USDT"
  - "BNB/USDT"
  - "XRP/USDT"
  - "ADA/USDT"
  - "DOGE/USDT"
  - "AVAX/USDT"
  - "LINK/USDT"
  - "DOT/USDT"

dashboard:
  host: "127.0.0.1"
  port: 8000
  chart_type: "candlestick"   # Options: "candlestick" or "line"
  timeframe: "1m"
```

### 3. Running the Agent

Launch the server and data collector:

```bash
.\.venv\Scripts\python main.py
```

Then open your browser at:
`http://127.0.0.1:8000`

---

## 📊 System Architecture

```
                 ┌───────────────────────────┐
                 │        config.yaml        │
                 └─────────────┬─────────────┘
                               │
                               ▼
 ┌───────────────────────────────────────────────────────────┐
 │               HIGH-FREQUENCY RATE COLLECTOR               │
 │  - Fetches ticker rates every 0.5s (500ms)               │
 │  - Broadcasts to WebSocket clients                        │
 └─────────────┬──────────────────────────────┬──────────────┘
               │                              │
               ▼                              ▼
 ┌───────────────────────────┐  ┌───────────────────────────┐
 │      STORAGE ENGINE       │  │     FASTAPI DASHBOARD     │
 │  - Raw 0.5s Ticks (7 Days)│  │  - WebSockets (/ws/rates) │
 │  - 1m Candles (90 Days)   │  │  - Interactive Chart UI   │
 └───────────────────────────┘  └───────────────────────────┘
```
