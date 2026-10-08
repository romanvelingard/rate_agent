import asyncio
import logging
from contextlib import asynccontextmanager
import uvicorn
from src.config import load_config
from src.storage import StorageEngine
from src.collector import RateCollector
from src.alerts import AlertManager
from src.server import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

def main():
    logger.info("Initializing Crypto Rate Agent...")
    
    # 1. Load configuration from config.yaml
    config = load_config("config.yaml")
    logger.info(f"Loaded configuration for exchange '{config.exchange}' with {len(config.currencies)} currencies.")

    # 2. Initialize dual-tier SQLite database engine
    storage = StorageEngine(
        db_path=config.storage.db_path,
        tick_retention_days=config.storage.tick_retention_days,
        candle_retention_days=config.storage.candle_retention_days
    )

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
