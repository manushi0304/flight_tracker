"""
SQLite persistence layer.

Schema (table: fares):
    id          INTEGER PRIMARY KEY AUTOINCREMENT
    route       TEXT    NOT NULL   -- e.g. 'BOM-SYD'
    date        TEXT    NOT NULL   -- flight date, ISO 'YYYY-MM-DD'
    price       INTEGER NOT NULL   -- price in INR
    checked_at  TEXT    NOT NULL   -- ISO datetime of when this check happened

Every fetch inserts a new row (append-only history). "Last known price" for a
route+date is simply the most recent row for that route+date.
"""
import sqlite3
from contextlib import contextmanager
from datetime import date as date_type, datetime, timedelta
from pathlib import Path
from typing import Iterator, List, Optional

from config import settings
from models import FareRecord, WeeklySummaryItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS fares (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    route       TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    price       INTEGER NOT NULL,
    checked_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fares_route_date ON fares(route, date);
CREATE INDEX IF NOT EXISTS idx_fares_checked_at ON fares(checked_at);
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")  # safe for a single writer + occasional reads
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create the fares table if it doesn't already exist. Safe to call every startup."""
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True) if Path(settings.DB_PATH).parent != Path("") else None
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def save_fare(route: str, flight_date: date_type, price: int, checked_at: Optional[datetime] = None) -> None:
    """Insert a new price observation."""
    checked_at = checked_at or datetime.utcnow()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO fares (route, date, price, checked_at) VALUES (?, ?, ?, ?)",
            (route, flight_date.isoformat(), price, checked_at.isoformat()),
        )


def get_last_price(route: str, flight_date: date_type) -> Optional[int]:
    """Return the most recent previously-stored price for route+date, or None if never checked."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT price FROM fares WHERE route = ? AND date = ? ORDER BY checked_at DESC LIMIT 1",
            (route, flight_date.isoformat()),
        ).fetchone()
        return row["price"] if row else None


def get_history(route: str, flight_date: date_type) -> List[FareRecord]:
    """Full price history for a route+date, most recent first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT route, date, price, checked_at FROM fares WHERE route = ? AND date = ? ORDER BY checked_at DESC",
            (route, flight_date.isoformat()),
        ).fetchall()
        return [
            FareRecord(
                route=r["route"],
                flight_date=date_type.fromisoformat(r["date"]),
                price=r["price"],
                checked_at=datetime.fromisoformat(r["checked_at"]),
            )
            for r in rows
        ]


def get_weekly_cheapest(routes: List[str], since: Optional[datetime] = None) -> List[WeeklySummaryItem]:
    """
    For each route, find the cheapest price recorded since `since` (default: 7 days ago)
    along with which flight date that fare was for, and how many observations were made.
    """
    since = since or (datetime.utcnow() - timedelta(days=7))
    results: List[WeeklySummaryItem] = []
    with get_conn() as conn:
        for route in routes:
            row = conn.execute(
                """
                SELECT date, price FROM fares
                WHERE route = ? AND checked_at >= ?
                ORDER BY price ASC, checked_at DESC
                LIMIT 1
                """,
                (route, since.isoformat()),
            ).fetchone()
            count_row = conn.execute(
                "SELECT COUNT(*) as c FROM fares WHERE route = ? AND checked_at >= ?",
                (route, since.isoformat()),
            ).fetchone()
            if row:
                results.append(
                    WeeklySummaryItem(
                        route=route,
                        cheapest_price=row["price"],
                        cheapest_date=date_type.fromisoformat(row["date"]),
                        samples_count=count_row["c"] if count_row else 0,
                    )
                )
    return results
