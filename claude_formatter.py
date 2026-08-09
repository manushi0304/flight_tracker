"""
Uses the Claude API purely for turning structured data into a short, natural
Telegram message. If the API call fails for any reason, we fall back to a
plain template so a notification always goes out.

COST NOTE: this is the only part of the whole system that isn't free. If
ANTHROPIC_API_KEY is left blank in .env / secrets, this module skips the API
entirely and uses the plain-text templates below -- $0, no Anthropic billing
required. Set ANTHROPIC_API_KEY to opt into nicer-sounding messages (usage
here is tiny -- a few cents a month at most).
"""
import logging
from typing import List, Optional

from config import settings
from models import PriceDrop, WeeklySummaryItem

logger = logging.getLogger("claude_formatter")

MODEL = "claude-sonnet-4-6"

_client: Optional["anthropic.Anthropic"] = None
if settings.ANTHROPIC_API_KEY:
    import anthropic
    _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _call_claude(prompt: str, fallback: str) -> str:
    if _client is None:
        # No API key configured -- free mode, use the template as-is.
        return fallback
    try:
        resp = _client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text").strip()
        return text or fallback
    except Exception as e:
        logger.warning("Claude formatting failed, using fallback template: %s", e)
        return fallback


def format_price_drop_message(drop: PriceDrop) -> str:
    fallback = (
        f"✈️ Price drop! {drop.route} on {drop.flight_date.isoformat()}\n"
        f"₹{drop.old_price:,} → ₹{drop.new_price:,} (down ₹{drop.drop_amount:,})"
    )
    prompt = (
        "Write a short, excited Telegram message (max 3 sentences, can use 1-2 emoji) "
        "announcing a flight price drop. Do not add a greeting or sign-off, just the alert. "
        f"Route: {drop.route} (one-way, economy). Flight date: {drop.flight_date.isoformat()}. "
        f"Previous price: INR {drop.old_price}. New price: INR {drop.new_price}. "
        f"Drop amount: INR {drop.drop_amount}."
    )
    return _call_claude(prompt, fallback)


def format_weekly_digest(items: List[WeeklySummaryItem]) -> str:
    if not items:
        fallback = "📊 Weekly flight digest: no price data collected this week."
    else:
        lines = ["📊 Weekly flight digest -- cheapest fares this week:"]
        for item in items:
            lines.append(f"{item.route}: ₹{item.cheapest_price:,} on {item.cheapest_date.isoformat()}")
        fallback = "\n".join(lines)

    if not items:
        return fallback

    data_lines = "\n".join(
        f"- {i.route}: cheapest INR {i.cheapest_price} for flight date {i.cheapest_date.isoformat()} "
        f"(from {i.samples_count} checks this week)"
        for i in items
    )
    prompt = (
        "Write a short, friendly Telegram weekly digest message (max 6 lines, 1-2 emoji) "
        "summarizing the cheapest one-way economy flight fare found per route this week. "
        "Use one line per route. No greeting or sign-off, just the summary.\n\n"
        f"Data:\n{data_lines}"
    )
    return _call_claude(prompt, fallback)
