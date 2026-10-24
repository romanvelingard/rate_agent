import asyncio
import logging
import argparse
from contextlib import asynccontextmanager
import uvicorn
from src.config import load_config
from src.storage import get_storage_engine
from src.collector import RateCollector
from src.alerts import AlertManager
from src.server import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

def parse_args():
    parser = argparse.ArgumentParser(description="Crypto Rate Agent - Real-Time Exchange Rate Monitor")
    parser.add_argument(
        "--no-db", action="store_true",
        help="Run in No-DB mode (pure RAM buffer + CSV logging, strictly limited to 3 crypto pairs to conserve memory)"
    )
    parser.add_argument(
        "--memory", action="store_true",
        help="Alias for --no-db"
    )
    parser.add_argument(
        "--csv-dir", type=str, default=None,
        help="Directory for separate crypto CSV files when running in No-DB mode (default: data)"
    )
    parser.add_argument(
        "--csv-path", type=str, default=None,
        help="Alias for --csv-dir"
    )
    parser.add_argument(
        "--host", type=str, default=None,
        help="Host to bind Web Dashboard (default from config.yaml)"
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Port to bind Web Dashboard (default from config.yaml)"
    )
    parser.add_argument(
        "--config", type=str, default="config.yaml",
        help="Path to YAML configuration file"
    )
    return parser.parse_args()

def main():
    args = parse_args()
    logger.info("Initializing Crypto Rate Agent...")
    
    # 1. Load configuration from YAML
    config = load_config(args.config)
    
    if args.host:
        config.dashboard.host = args.host
    if args.port:
        config.dashboard.port = args.port
    if args.csv_dir:
        config.storage.csv_dir = args.csv_dir
    elif args.csv_path:
        config.storage.csv_dir = args.csv_path

    # Check if No-DB mode is requested via CLI or config.yaml
    is_no_db = (
        args.no_db
        or args.memory
        or not config.storage.enabled
        or config.storage.mode.lower() in ("memory", "in-memory", "csv", "none", "disabled")
    )

    # In No-DB / In-Memory mode, strictly enforce maximum of 3 crypto symbols to prevent memory exhaustion
    if is_no_db:
        max_symbols = config.storage.max_memory_symbols or 3
        if len(config.currencies) > max_symbols:
            logger.warning(
                f"⚡ No-DB / In-Memory mode active: strictly capping monitored pairs to {max_symbols} "
                f"cryptos to keep RAM usage minimal. Selected: {config.currencies[:max_symbols]}"
            )
            config.currencies = config.currencies[:max_symbols]
        csv_files = [f"{s.replace('/', '_')}.csv" for s in config.currencies]
        logger.info(f"⚡ Mode: NO-DB (RAM buffer + separate CSV files in '{config.storage.csv_dir}/': {csv_files})")
    else:
        logger.info(f"💾 Mode: SQLite Database ('{config.storage.db_path}' with WAL)")

    logger.info(f"Loaded configuration for exchange '{config.exchange}' with {len(config.currencies)} currencies: {config.currencies}")

    # 2. Initialize storage engine (SQLite or InMemory with CSV)
    storage = get_storage_engine(config.storage, no_db=is_no_db)

    # 3. Initialize Alert Manager (Telegram & Discord)
    alert_mgr = AlertManager(
        telegram_token=config.alerts.telegram.token,
        telegram_chat_id=config.alerts.telegram.chat_id,
        discord_webhook_url=config.alerts.discord.webhook_url
    )

    # 4. Initialize High-Frequency Rate Collector
    collector = RateCollector(config, storage)

    # Lifespan Context Manager replacing deprecated on_event
    @asynccontextmanager
    async def lifespan(app):
        logger.info("Starting background RateCollector task...")
        collector_task = asyncio.create_task(collector.start())
        yield
        logger.info("Stopping RateCollector background task...")
        await collector.stop()
        collector_task.cancel()

    # 5. Create FastAPI Web Server & WebSocket Hub
    app = create_app(config, storage, collector, alert_mgr, lifespan=lifespan)

    # 6. Launch Web Server
    logger.info(f"Starting Web Dashboard server at http://{config.dashboard.host}:{config.dashboard.port}")
    uvicorn.run(app, host=config.dashboard.host, port=config.dashboard.port, log_level="info")

if __name__ == "__main__":
    main()

