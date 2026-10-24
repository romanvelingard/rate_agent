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

---

## 🚀 Quick Start & Local Execution

### 1. Ready-to-Use Local Virtual Environment
The virtual environment is already initialized in `.venv` with all dependencies installed.

### 2. Execution Modes

#### ⚡ Mode A: Lightweight Local Run (No-DB + CSV Logging)
Zero database overhead. Strictly limits memory to **up to 3 crypto pairs** with small bounded buffers in RAM and records each crypto's rate data directly into its own separate CSV file (e.g. `data/BTC_USDT.csv`, `data/ETH_USDT.csv`, `data/SOL_USDT.csv`):

```bash
# Option 1: Double click or run batch script
run.bat --no-db

# Option 2: PowerShell script
.\run.ps1 --no-db

# Option 3: Direct Python command
.\.venv\Scripts\python main.py --no-db
```

#### 💾 Mode B: Persistent SQLite WAL Mode
Saves sub-second ticks (7-day retention) and 1m candles (90-day retention) in SQLite database:

```bash
run.bat
# or
.\.venv\Scripts\python main.py
```

### 3. Open Web Dashboard
Once started, open your browser at:
👉 **`http://127.0.0.1:8000`**

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
