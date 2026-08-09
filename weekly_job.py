"""
Weekly job (runs Monday only, after the daily job):
  - For each route, find the cheapest fare observed across ALL tracked dates
    in the last 7 days of checks.
  - Send one WhatsApp digest message covering all routes.

This always sends, regardless of whether any instant price-drop alerts fired
that week (per requirement: "sent regardless of rule 1").
"""
import logging

from claude_formatter import format_weekly_digest
from config import settings
from database import get_weekly_cheapest, init_db
from models import route_code
from telegram_sender import send_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("weekly_job")


def run_weekly_job() -> None:
    logger.info("=== Weekly job started ===")
    init_db()

    routes = [route_code(o, d) for o, d in settings.route_pairs()]
    items = get_weekly_cheapest(routes)

    if not items:
        logger.warning("No fare data found for the past week -- sending digest anyway to confirm the job ran.")

    message = format_weekly_digest(items)
    sent = send_telegram(message)

    logger.info("=== Weekly job finished: digest_sent=%s, routes_covered=%d ===", sent, len(items))


if __name__ == "__main__":
    run_weekly_job()
