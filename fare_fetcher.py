"""
Wraps the `fast-flights` Google Flights scraper.

fast-flights scrapes Google's HTML/JS output, which means:
  - it has NO API key / auth, but
  - it can break silently whenever Google changes their markup, and
  - it can get you rate-limited if you hammer it.

This module therefore:
  - retries transient failures with exponential backoff (tenacity)
  - never raises out to the caller -- always returns a FetchResult
  - parses whatever price string Google returns into a clean INR integer
  - requests INR pricing explicitly (falls back to whatever currency
    Google gives us if the installed fast-flights version doesn't support
    a `currency` kwarg -- see NOTE below)
"""
import logging
import re
from datetime import date as date_type
from typing import List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings
from models import FetchResult, route_code

logger = logging.getLogger("fare_fetcher")

PRICE_RE = re.compile(r"[\d,]+")


class FareFetchError(Exception):
    """Raised internally when a scrape attempt fails; caught by the retry wrapper."""


def _parse_price(raw: str) -> Optional[int]:
    """
    Turn something like '₹45,231' / 'INR 45,231' / '$542' into an int.
    Returns None if no digits could be found (e.g. 'Price unavailable').
    """
    if not raw:
        return None
    match = PRICE_RE.search(raw)
    if not match:
        return None
    digits = match.group(0).replace(",", "")
    try:
        return int(digits)
    except ValueError:
        return None


@retry(
    stop=stop_after_attempt(settings.MAX_RETRIES),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(FareFetchError),
    reraise=True,
)
def _scrape_cheapest_price(origin: str, dest: str, flight_date: date_type) -> int:
    """
    Single scrape attempt (retried by tenacity). Raises FareFetchError on any
    failure so the retry decorator kicks in; returns the cheapest INR price found.
    """
    try:
        from fast_flights import FlightData, Passengers, create_filter, get_flights_from_filter
    except ImportError as e:
        raise FareFetchError(f"fast-flights not installed correctly: {e}")

    try:
        flight_filter = create_filter(
            flight_data=[
                FlightData(date=flight_date.isoformat(), from_airport=origin, to_airport=dest)
            ],
            trip="one-way",
            seat="economy",
            passengers=Passengers(adults=1, children=0, infants_in_seat=0, infants_on_lap=0),
        )
    except Exception as e:
        raise FareFetchError(f"failed to build search filter: {e}")

    try:
        # currency kwarg is supported by get_flights_from_filter in recent
        # fast-flights versions; if a pinned older version rejects it, retry
        # once without it so the whole job doesn't hard-fail.
        try:
            result = get_flights_from_filter(flight_filter, currency=settings.CURRENCY, mode="fallback")
        except TypeError:
            result = get_flights_from_filter(flight_filter, mode="fallback")
    except AssertionError as e:
        # fast-flights raises AssertionError on non-200 responses (e.g. Google blocked us)
        raise FareFetchError(f"scrape blocked or non-200 response: {e}")
    except Exception as e:
        raise FareFetchError(f"scrape request failed: {e}")

    if result is None or not getattr(result, "flights", None):
        raise FareFetchError("no flights returned (route/date may be invalid or unavailable)")

    prices = [_parse_price(f.price) for f in result.flights]
    prices = [p for p in prices if p is not None]
    if not prices:
        raise FareFetchError("flights returned but no parseable prices")

    return min(prices)


def fetch_fare(origin: str, dest: str, flight_date: date_type) -> FetchResult:
    """
    Public entry point. Always returns a FetchResult -- never raises.
    On failure, FetchResult.success is False and .error explains why.
    """
    route = route_code(origin, dest)
    try:
        price = _scrape_cheapest_price(origin, dest, flight_date)
        return FetchResult(route=route, flight_date=flight_date, price=price, success=True)
    except Exception as e:
        logger.warning("Fetch failed for %s on %s: %s", route, flight_date, e)
        return FetchResult(route=route, flight_date=flight_date, success=False, error=str(e))


def fetch_all(routes: List[tuple], dates: List[date_type], delay_seconds: float = None) -> List[FetchResult]:
    """
    Sequentially fetch every route x date combination, sleeping between requests
    to reduce the chance of being rate-limited / blocked by Google.
    """
    import time
    import random

    delay = settings.REQUEST_DELAY_SECONDS if delay_seconds is None else delay_seconds
    results: List[FetchResult] = []
    total = len(routes) * len(dates)
    done = 0

    for origin, dest in routes:
        for d in dates:
            result = fetch_fare(origin, dest, d)
            results.append(result)
            done += 1
            if done % 10 == 0 or done == total:
                logger.info("Fetched %d/%d fares", done, total)
            # jittered delay so requests aren't perfectly periodic
            time.sleep(delay + random.uniform(0, delay * 0.5))

    return results
