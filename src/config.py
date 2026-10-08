import os
import yaml
from pydantic import BaseModel, Field
from typing import List

class TelegramConfig(BaseModel):
    token: str = ""
    chat_id: str = ""

class DiscordConfig(BaseModel):
    webhook_url: str = ""

class AlertsConfig(BaseModel):
    enabled: bool = True
    min_confidence_score: float = 80.0
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)

class StorageConfig(BaseModel):
    db_path: str = "data/crypto_rates.db"
    tick_retention_days: int = 7
    candle_retention_days: int = 90

class DashboardConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    default_symbol: str = "BTC/USDT"
    chart_type: str = "candlestick"  # "candlestick" or "line"
    timeframe: str = "1m"

class AppConfig(BaseModel):
    exchange: str = "binance"
    update_interval_ms: int = 500
    currencies: List[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    storage: StorageConfig = Field(default_factory=StorageConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)

def load_config(config_path: str = "config.yaml") -> AppConfig:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {os.path.abspath(config_path)}")
    with open(config_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)
    return AppConfig(**raw_data)
