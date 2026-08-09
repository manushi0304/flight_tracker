"""
Compares a freshly-fetched price against the last stored price for the same
route+date, and decides whether it qualifies as a "drop" worth alerting on.
"""
import logging
from typing import Optional

from config import settings
from database import get_last_price
from models import FetchResult, PriceDrop

logger = logging.getLogger("price_comparator")


def evaluate_drop(fetch_result: FetchResult) -> Optional[PriceDrop]:
    """
    Look up the last stored price for this route+date and compare it to the
    newly fetched price.

    Returns a PriceDrop if:
      - there IS a previous price on record, AND
      - the new price is at least PRICE_DROP_THRESHOLD_INR cheaper.

    Returns None if there's no prior price (first-ever check) or the drop
    doesn't meet the threshold (including price increases / no change).
    """
    if not fetch_result.success or fetch_result.price is None:
        return None

    last_price = get_last_price(fetch_result.route, fetch_result.flight_date)
    if last_price is None:
        logger.debug("No prior price for %s on %s -- baseline only", fetch_result.route, fetch_result.flight_date)
        return None

    drop_amount = last_price - fetch_result.price
    if drop_amount >= settings.PRICE_DROP_THRESHOLD_INR:
        return PriceDrop(
            route=fetch_result.route,
            flight_date=fetch_result.flight_date,
            old_price=last_price,
            new_price=fetch_result.price,
        )
    return None
