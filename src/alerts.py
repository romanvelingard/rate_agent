import aiohttp
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class AlertManager:
    def __init__(self, telegram_token: Optional[str] = None, telegram_chat_id: Optional[str] = None, discord_webhook_url: Optional[str] = None):
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.discord_webhook_url = discord_webhook_url

    async def send_alert(self, title: str, message: str, level: str = "INFO"):
        emoji = "🚀" if level == "BULLISH" else ("⚠️" if level == "BEARISH" else "ℹ️")
        formatted_msg = f"{emoji} *{title}*\n\n{message}"

        # 1. Send Telegram Notification
        if self.telegram_token and self.telegram_chat_id:
            await self._send_telegram(formatted_msg)

        # 2. Send Discord Webhook Notification
        if self.discord_webhook_url:
            await self._send_discord(title, message, level)

    async def _send_telegram(self, text: str):
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=5) as resp:
                    if resp.status != 200:
                        logger.error(f"Telegram alert failed with HTTP {resp.status}")
                    else:
                        logger.info("Telegram alert sent successfully.")
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

    async def _send_discord(self, title: str, message: str, level: str):
        color = 0x10b981 if level == "BULLISH" else (0xef4444 if level == "BEARISH" else 0x3b82f6)
        payload = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": color
            }]
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.discord_webhook_url, json=payload, timeout=5) as resp:
                    if resp.status not in (200, 204):
                        logger.error(f"Discord webhook alert failed with HTTP {resp.status}")
                    else:
                        logger.info("Discord alert sent successfully.")
        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")
