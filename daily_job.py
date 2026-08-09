"""
Daily job (runs once a day, every day):
  1. Fetch current price for every tracked route x date combination.
  2. For each successful fetch, compare against the last stored price.
  3. If the price dropped by >= PRICE_DROP_THRESHOLD_INR, send an instant WhatsApp alert.
  4. Save every successful fetch to the database (so tomorrow has something to compare against).

Failed fetches (scrape errors) are logged and skipped -- they do NOT get saved,
so a transient failure never gets treated as a fake "price" in future comparisons.
"""
import logging
from datetime import datetime

from claude_formatter import format_price_drop_message
from config import settings
from database import init_db, save_fare
from fare_fetcher import fetch_all
from price_comparator import evaluate_drop
from telegram_sender import send_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("daily_job")


def run_daily_job() -> None:
    logger.info("=== Daily job started ===")
    init_db()

    routes = settings.route_pairs()
    dates = settings.date_range()
    logger.info("Checking %d routes x %d dates = %d fares", len(routes), len(dates), len(routes) * len(dates))

    results = fetch_all(routes, dates)

    saved, failed, alerts_sent = 0, 0, 0
    checked_at = datetime.utcnow()

    for result in results:
        if not result.success or result.price is None:
            failed += 1
            continue

        drop = evaluate_drop(result)
        if drop:
            message = format_price_drop_message(drop)
            if send_telegram(message):
                alerts_sent += 1
            else:
                logger.error("Failed to send alert for %s on %s", drop.route, drop.flight_date)

        save_fare(result.route, result.flight_date, result.price, checked_at=checked_at)
        saved += 1

    logger.info(
        "=== Daily job finished: %d saved, %d failed fetches, %d alerts sent ===",
        saved, failed, alerts_sent,
    )


if __name__ == "__main__":
    run_daily_job()
