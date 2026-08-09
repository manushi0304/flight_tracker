"""
Sends alert/digest messages via the Telegram Bot API. Completely free, no
trial expiry, no card required -- unlike Twilio's 30-day trial.

Setup (see README): message @BotFather on Telegram to create a bot and get
a token, then message your bot once and fetch your chat_id via the
getUpdates endpoint. Both go in .env / GitHub Actions secrets.
"""
import logging

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger("telegram_sender")

MAX_MSG_LEN = 4000  # Telegram's limit is 4096 chars; leave a safety margin
API_BASE = "https://api.telegram.org"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _send_single(text: str) -> None:
    url = f"{API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": text},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API returned {resp.status_code}: {resp.text}")


def send_telegram(message: str) -> bool:
    """
    Send a Telegram message, splitting into multiple messages if too long.
    Returns True if all chunks sent successfully, False otherwise (logged, not raised --
    a failed notification should not crash the scheduler).
    """
    chunks = [message[i : i + MAX_MSG_LEN] for i in range(0, len(message), MAX_MSG_LEN)] or [message]
    try:
        for chunk in chunks:
            _send_single(chunk)
        logger.info("Telegram message sent (%d chunk(s))", len(chunks))
        return True
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)
        return False
