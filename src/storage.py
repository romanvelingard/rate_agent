import os
import sqlite3
import time
import logging
import csv
from datetime import datetime, timezone
from collections import defaultdict, deque
from typing import List, Dict, Any, Optional, Set

logger = logging.getLogger(__name__)

class StorageEngine:
    def __init__(self, db_path: str, tick_retention_days: int = 7, candle_retention_days: int = 90):
        self.db_path = db_path
        self.tick_retention_days = tick_retention_days
        self.candle_retention_days = candle_retention_days
        self.is_in_memory: bool = False
        self.storage_type: str = "sqlite"
        
        # Ensure database directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging (WAL) for high concurrency sub-second performance
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            # 1. Raw Ticks Table (0.5s checks)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL DEFAULT 0,
                    bid REAL DEFAULT 0,
                    ask REAL DEFAULT 0
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_sym_ts ON ticks(symbol, timestamp);")

            # 2. Aggregated 1-Minute Candles Table (Long-Term Retention)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candles_1m (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL DEFAULT 0,
                    count INTEGER DEFAULT 1,
                    UNIQUE(exchange, symbol, timestamp)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_candles_sym_ts ON candles_1m(symbol, timestamp);")
            conn.commit()
            logger.info("SQLite database initialized successfully with WAL mode.")

    def save_ticks_batch(self, ticks: List[Dict[str, Any]]):
        if not ticks:
            return
        
        with self.get_connection() as conn:
            # Insert ticks
            conn.executemany("""
                INSERT INTO ticks (timestamp, exchange, symbol, price, volume, bid, ask)
                VALUES (:timestamp, :exchange, :symbol, :price, :volume, :bid, :ask);
            """, ticks)
            
            # Upsert into 1-minute candles
            for t in ticks:
                # Floor timestamp to 1-minute boundary (60s)
                minute_ts = float(int(t['timestamp'] // 60) * 60)
                conn.execute("""
                    INSERT INTO candles_1m (timestamp, exchange, symbol, open, high, low, close, volume, count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(exchange, symbol, timestamp) DO UPDATE SET
                        high = MAX(candles_1m.high, excluded.open),
                        low = MIN(candles_1m.low, excluded.open),
                        close = excluded.open,
                        volume = candles_1m.volume + excluded.volume,
                        count = candles_1m.count + 1;
                """, (minute_ts, t['exchange'], t['symbol'], t['price'], t['price'], t['price'], t['price'], t.get('volume', 0)))
            
            conn.commit()

    def purge_expired_data(self):
        now = time.time()
        tick_cutoff = now - (self.tick_retention_days * 86400)
        candle_cutoff = now - (self.candle_retention_days * 86400)

        with self.get_connection() as conn:
            c1 = conn.execute("DELETE FROM ticks WHERE timestamp < ?;", (tick_cutoff,))
            c2 = conn.execute("DELETE FROM candles_1m WHERE timestamp < ?;", (candle_cutoff,))
            conn.commit()
            logger.info(f"Purged {c1.rowcount} expired raw ticks (< {self.tick_retention_days}d) and {c2.rowcount} expired 1m candles.")

    def get_recent_ticks(self, symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT timestamp, exchange, symbol, price, volume, bid, ask
                FROM ticks
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?;
            """, (symbol, limit))
            rows = [dict(r) for r in cursor.fetchall()]
            rows.reverse()
            return rows

    def get_candles(self, symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT timestamp, exchange, symbol, open, high, low, close, volume, count
                FROM candles_1m
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?;
            """, (symbol, limit))
            rows = [dict(r) for r in cursor.fetchall()]
            rows.reverse()
            return rows

    def get_symbol_stats_24h(self, symbol: str) -> Dict[str, Any]:
        now = time.time()
        day_ago = now - 86400
        week_ago = now - (7 * 86400)

        with self.get_connection() as conn:
            row_latest = conn.execute("""
                SELECT price FROM ticks WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1;
            """, (symbol,)).fetchone()
            
            latest_price = row_latest['price'] if row_latest else 0.0

            row_24h = conn.execute("""
                SELECT price FROM ticks WHERE symbol = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1;
            """, (symbol, day_ago)).fetchone()
            
            price_24h_ago = row_24h['price'] if row_24h else latest_price

            row_7d = conn.execute("""
                SELECT price FROM ticks WHERE symbol = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1;
            """, (symbol, week_ago)).fetchone()
            
            price_7d_ago = row_7d['price'] if row_7d else latest_price

            row_stats = conn.execute("""
                SELECT MAX(price) as high_24h, MIN(price) as low_24h, SUM(volume) as volume_24h
                FROM ticks WHERE symbol = ? AND timestamp >= ?;
            """, (symbol, day_ago)).fetchone()

            change_24h_pct = ((latest_price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago > 0 else 0.0
            change_7d_pct = ((latest_price - price_7d_ago) / price_7d_ago * 100) if price_7d_ago > 0 else 0.0

            return {
                "symbol": symbol,
                "latest_price": latest_price,
                "change_24h_pct": round(change_24h_pct, 2),
                "change_7d_pct": round(change_7d_pct, 2),
                "high_24h": row_stats['high_24h'] or latest_price,
                "low_24h": row_stats['low_24h'] or latest_price,
                "volume_24h": row_stats['volume_24h'] or 0.0
            }


class InMemoryStorageEngine:
    """
    Pure In-Memory storage engine with separate CSV files per crypto pair.
    - Limits tracked symbols to up to max_symbols (default 3) to minimize RAM footprint.
    - Uses small bounded deques for ticks and candles in memory.
    - Appends each crypto's rate data to its own dedicated CSV file (e.g. data/BTC_USDT.csv, data/ETH_USDT.csv, data/SOL_USDT.csv).
    - Preloads recent records from existing CSV files on launch if available.
    """
    def __init__(
        self,
        max_symbols: int = 3,
        max_ticks: int = 500,
        max_candles: int = 300,
        csv_dir: str = "data",
        record_csv: bool = True
    ):
        self.max_symbols = max_symbols
        self.max_ticks = max_ticks
        self.max_candles = max_candles
        self.csv_dir = csv_dir
        self.record_csv = record_csv
        self.is_in_memory: bool = True
        self.storage_type: str = "memory"

        # Allowed tracked crypto pairs (limited strictly up to max_symbols)
        self._allowed_symbols: Set[str] = set()

        # In-memory storage buffers per symbol (strictly bounded to save RAM)
        self._ticks: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.max_ticks))
        self._candles: Dict[str, Dict[float, Dict[str, Any]]] = defaultdict(dict)
        self._latest_price: Dict[str, float] = {}

        logger.info(
            f"InMemoryStorageEngine initialized: strictly capped to {self.max_symbols} crypto symbols, "
            f"{self.max_ticks} ticks/sym, {self.max_candles} candles/sym in RAM. "
            f"Separate CSV files directory: '{self.csv_dir}/'."
        )

        # Initialize CSV logging directory and preload if enabled
        if self.record_csv and self.csv_dir:
            os.makedirs(os.path.abspath(self.csv_dir), exist_ok=True)
            self._load_recent_csv_data()

    def _get_csv_path_for_symbol(self, symbol: str) -> str:
        """Derives a clean filename for each crypto pair (e.g. data/BTC_USDT.csv)."""
        clean_sym = symbol.replace("/", "_").replace(":", "_").replace("-", "_")
        return os.path.join(self.csv_dir, f"{clean_sym}.csv")

    def _init_symbol_csv(self, symbol: str):
        """Creates the individual symbol CSV file with headers if it does not already exist."""
        filepath = self._get_csv_path_for_symbol(symbol)
        try:
            if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                with open(filepath, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["timestamp", "datetime_utc", "exchange", "symbol", "price", "volume", "bid", "ask"])
                logger.info(f"Initialized CSV logger file for '{symbol}' at '{filepath}'.")
        except Exception as e:
            logger.error(f"Failed to initialize CSV file '{filepath}': {e}")

    def _load_recent_csv_data(self):
        """Preloads recent ticks from existing per-symbol CSV files into RAM buffers."""
        if not os.path.exists(self.csv_dir):
            return
        try:
            for fname in os.listdir(self.csv_dir):
                if not fname.endswith(".csv"):
                    continue
                filepath = os.path.join(self.csv_dir, fname)
                with open(filepath, "r", encoding="utf-8") as f:
                    reader = list(csv.DictReader(f))
                    if not reader:
                        continue
                    # Take only last 300 rows to keep memory usage minimal
                    recent_rows = reader[-300:]
                    loaded_ticks = []
                    for r in recent_rows:
                        try:
                            sym = r.get("symbol", "")
                            if not sym:
                                continue
                            if sym not in self._allowed_symbols and len(self._allowed_symbols) < self.max_symbols:
                                self._allowed_symbols.add(sym)

                            if sym in self._allowed_symbols:
                                loaded_ticks.append({
                                    "timestamp": float(r["timestamp"]),
                                    "exchange": r.get("exchange", ""),
                                    "symbol": sym,
                                    "price": float(r["price"]),
                                    "volume": float(r.get("volume", 0) or 0),
                                    "bid": float(r.get("bid", 0) or 0),
                                    "ask": float(r.get("ask", 0) or 0),
                                })
                        except (ValueError, KeyError):
                            continue

                    if loaded_ticks:
                        self._ingest_ticks_to_memory(loaded_ticks)
                        logger.info(f"Preloaded {len(loaded_ticks)} recent ticks from '{filepath}'.")
        except Exception as e:
            logger.warning(f"Could not preload recent history from CSV files: {e}")

    def _ingest_ticks_to_memory(self, ticks: List[Dict[str, Any]]):
        """Ingests ticks into the bounded RAM deques and aggregates 1-minute candles."""
        for t in ticks:
            sym = t['symbol']
            price = float(t['price'])
            vol = float(t.get('volume', 0.0))
            self._ticks[sym].append(dict(t))
            self._latest_price[sym] = price

            # 1-minute candle aggregation
            minute_ts = float(int(t['timestamp'] // 60) * 60)
            sym_candles = self._candles[sym]

            if minute_ts not in sym_candles:
                # Evict oldest candle if exceeding max_candles limit
                if len(sym_candles) >= self.max_candles:
                    oldest_ts = min(sym_candles.keys())
                    del sym_candles[oldest_ts]

                sym_candles[minute_ts] = {
                    "timestamp": minute_ts,
                    "exchange": t.get('exchange', ''),
                    "symbol": sym,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": vol,
                    "count": 1
                }
            else:
                c = sym_candles[minute_ts]
                c['high'] = max(c['high'], price)
                c['low'] = min(c['low'], price)
                c['close'] = price
                c['volume'] += vol
                c['count'] += 1

    def save_ticks_batch(self, ticks: List[Dict[str, Any]]):
        if not ticks:
            return

        valid_ticks = []
        for t in ticks:
            sym = t.get('symbol')
            if not sym:
                continue

            # Enforce max 3 symbols limit strictly
            if sym not in self._allowed_symbols:
                if len(self._allowed_symbols) < self.max_symbols:
                    self._allowed_symbols.add(sym)
                    self._init_symbol_csv(sym)
                    logger.info(
                        f"Registered crypto pair '{sym}' ({len(self._allowed_symbols)}/{self.max_symbols}). "
                        f"Logging to '{self._get_csv_path_for_symbol(sym)}'."
                    )
                else:
                    # Ignore additional cryptos beyond the 3 allowed
                    continue

            valid_ticks.append(t)

        if not valid_ticks:
            return

        # 1. Update in-memory rolling buffer
        self._ingest_ticks_to_memory(valid_ticks)

        # 2. Append to individual symbol CSV files
        if self.record_csv and self.csv_dir:
            by_sym = defaultdict(list)
            for t in valid_ticks:
                by_sym[t['symbol']].append(t)

            for sym, sym_ticks in by_sym.items():
                filepath = self._get_csv_path_for_symbol(sym)
                try:
                    self._init_symbol_csv(sym)
                    with open(filepath, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        for t in sym_ticks:
                            ts = t['timestamp']
                            dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                            writer.writerow([
                                ts,
                                dt_str,
                                t.get('exchange', ''),
                                t['symbol'],
                                t['price'],
                                t.get('volume', 0),
                                t.get('bid', 0),
                                t.get('ask', 0)
                            ])
                except Exception as e:
                    logger.error(f"Error appending ticks to CSV '{filepath}': {e}")

    def purge_expired_data(self):
        # In-memory ticks are automatically bounded by maxlen.
        # Prune candles older than 7 days from memory
        now = time.time()
        cutoff = now - (7 * 86400)
        purged = 0
        for sym_candles in self._candles.values():
            expired = [ts for ts in sym_candles if ts < cutoff]
            for ts in expired:
                del sym_candles[ts]
                purged += 1
        if purged > 0:
            logger.info(f"InMemoryStorageEngine purged {purged} expired RAM candles.")

    def get_recent_ticks(self, symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
        ticks = list(self._ticks.get(symbol, []))
        return ticks[-limit:] if len(ticks) > limit else ticks

    def get_candles(self, symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
        sym_candles = self._candles.get(symbol, {})
        sorted_candles = [sym_candles[ts] for ts in sorted(sym_candles.keys())]
        return sorted_candles[-limit:] if len(sorted_candles) > limit else sorted_candles

    def get_symbol_stats_24h(self, symbol: str) -> Dict[str, Any]:
        now = time.time()
        day_ago = now - 86400
        week_ago = now - (7 * 86400)

        ticks = list(self._ticks.get(symbol, []))
        if not ticks:
            latest_price = self._latest_price.get(symbol, 0.0)
            return {
                "symbol": symbol,
                "latest_price": latest_price,
                "change_24h_pct": 0.0,
                "change_7d_pct": 0.0,
                "high_24h": latest_price,
                "low_24h": latest_price,
                "volume_24h": 0.0
            }

        latest_price = ticks[-1]['price']

        # Price 24h ago
        price_24h_ago = latest_price
        for t in reversed(ticks):
            if t['timestamp'] <= day_ago:
                price_24h_ago = t['price']
                break
        else:
            price_24h_ago = ticks[0]['price']

        # Price 7d ago
        price_7d_ago = latest_price
        for t in reversed(ticks):
            if t['timestamp'] <= week_ago:
                price_7d_ago = t['price']
                break
        else:
            price_7d_ago = ticks[0]['price']

        recent_24h_ticks = [t for t in ticks if t['timestamp'] >= day_ago]
        if recent_24h_ticks:
            high_24h = max(t['price'] for t in recent_24h_ticks)
            low_24h = min(t['price'] for t in recent_24h_ticks)
            volume_24h = sum(t.get('volume', 0.0) for t in recent_24h_ticks)
        else:
            high_24h = latest_price
            low_24h = latest_price
            volume_24h = 0.0

        change_24h_pct = ((latest_price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago > 0 else 0.0
        change_7d_pct = ((latest_price - price_7d_ago) / price_7d_ago * 100) if price_7d_ago > 0 else 0.0

        return {
            "symbol": symbol,
            "latest_price": latest_price,
            "change_24h_pct": round(change_24h_pct, 2),
            "change_7d_pct": round(change_7d_pct, 2),
            "high_24h": high_24h,
            "low_24h": low_24h,
            "volume_24h": round(volume_24h, 2)
        }


def get_storage_engine(config, no_db: bool = False):
    """
    Factory returning either persistent SQLite StorageEngine or lightweight InMemoryStorageEngine (with separate CSV files).
    """
    mode = getattr(config, "mode", "sqlite").lower()
    enabled = getattr(config, "enabled", True)

    if no_db or not enabled or mode in ("memory", "in-memory", "csv", "none", "disabled"):
        csv_dir = getattr(config, "csv_dir", "data")
        logger.info(
            f"Operating in NO-DB / In-Memory mode. No SQLite database files will be created. "
            f"Separate CSV files logged in directory: '{csv_dir}/'"
        )
        return InMemoryStorageEngine(
            max_symbols=getattr(config, "max_memory_symbols", 3),
            max_ticks=getattr(config, "max_memory_ticks", 500),
            max_candles=getattr(config, "max_memory_candles", 300),
            csv_dir=csv_dir,
            record_csv=getattr(config, "record_csv", True)
        )
    else:
        logger.info(f"Operating in persistent SQLite mode. Database path: '{config.db_path}' (WAL enabled).")
        return StorageEngine(
            db_path=config.db_path,
            tick_retention_days=config.tick_retention_days,
            candle_retention_days=config.candle_retention_days
        )



