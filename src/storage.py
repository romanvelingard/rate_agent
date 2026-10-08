import os
import sqlite3
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class StorageEngine:
    def __init__(self, db_path: str, tick_retention_days: int = 7, candle_retention_days: int = 90):
        self.db_path = db_path
        self.tick_retention_days = tick_retention_days
        self.candle_retention_days = candle_retention_days
        
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
