import asyncio
import json
import logging
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from src.config import AppConfig
from src.storage import StorageEngine
from src.collector import RateCollector
from src.analytics import AnalyticsEngine

from src.alerts import AlertManager

logger = logging.getLogger(__name__)

def create_app(config: AppConfig, storage: StorageEngine, collector: RateCollector, alert_mgr: AlertManager = None, lifespan = None) -> FastAPI:
    app = FastAPI(title="Crypto Rate Agent", version="1.0.0", lifespan=lifespan)

    # Store active websocket connections
    active_websockets: Set[WebSocket] = set()

    # Callback when new tick arrives from collector
    def broadcast_tick(tick: dict):
        if not active_websockets:
            return
        payload = json.dumps({"type": "tick", "data": tick})
        dead_sockets = set()
        for ws in list(active_websockets):
            try:
                asyncio.run_coroutine_threadsafe(ws.send_text(payload), asyncio.get_event_loop())
            except Exception:
                dead_sockets.add(ws)
        active_websockets.difference_update(dead_sockets)

    collector.subscribe(broadcast_tick)

    # REST Routes
    @app.get("/api/config")
    async def get_config():
        return {
            "exchange": config.exchange,
            "update_interval_ms": config.update_interval_ms,
            "currencies": config.currencies,
            "chart_type": config.dashboard.chart_type,
            "default_symbol": config.dashboard.default_symbol,
            "timeframe": config.dashboard.timeframe,
            "storage_mode": getattr(storage, "storage_type", "sqlite"),
            "is_in_memory": getattr(storage, "is_in_memory", False),
            "csv_dir": getattr(storage, "csv_dir", "data")
        }

    @app.get("/api/symbols")
    async def get_symbols():
        stats = []
        for sym in config.currencies:
            st = storage.get_symbol_stats_24h(sym)
            stats.append(st)
        return {"symbols": stats}

    @app.get("/api/history/{symbol:path}")
    async def get_history(symbol: str, limit: int = 300, mode: str = "candles"):
        # symbol can be passed encoded or as BTC/USDT
        symbol = symbol.replace("%2F", "/")
        if mode == "ticks":
            data = storage.get_recent_ticks(symbol, limit=limit)
        else:
            data = storage.get_candles(symbol, limit=limit)
        return {"symbol": symbol, "data": data}

    @app.get("/api/analysis/{symbol:path}")
    async def get_analysis(symbol: str):
        symbol = symbol.replace("%2F", "/")
        candles = storage.get_candles(symbol, limit=200)
        stats = storage.get_symbol_stats_24h(symbol)
        indicators = AnalyticsEngine.calculate_indicators(candles)
        return {
            "stats": stats,
            "analysis": indicators
        }

    # WebSocket Endpoint
    @app.websocket("/ws/rates")
    async def websocket_rates(websocket: WebSocket):
        await websocket.accept()
        active_websockets.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(active_websockets)}")
        try:
            # Send initial snapshot of all current prices
            await websocket.send_text(json.dumps({
                "type": "snapshot",
                "data": collector.latest_tickers
            }))
            while True:
                # Keep alive check
                await websocket.receive_text()
        except WebSocketDisconnect:
            active_websockets.remove(websocket)
            logger.info("WebSocket client disconnected.")
        except Exception as e:
            active_websockets.discard(websocket)
            logger.error(f"WebSocket error: {e}")

    # Static Assets & Frontend UI
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/")
    async def get_dashboard():
        return FileResponse("static/index.html")

    return app
