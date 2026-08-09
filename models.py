"""
Pydantic models shared across the fetching, comparison, DB, and notification layers.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def route_code(origin: str, dest: str) -> str:
    return f"{origin.upper()}-{dest.upper()}"


class FareRecord(BaseModel):
    """One price observation for a route+date, as stored in / read from SQLite."""

    route: str = Field(..., description="e.g. 'BOM-SYD'")
    flight_date: date
    price: int = Field(..., ge=0, description="Price in INR (integer, no decimals)")
    checked_at: datetime

    @field_validator("route")
    @classmethod
    def route_format(cls, v: str) -> str:
        if "-" not in v or len(v.split("-")) != 2:
            raise ValueError("route must be in 'ORIGIN-DEST' format, e.g. 'BOM-SYD'")
        return v.upper()


class FetchResult(BaseModel):
    """Outcome of a single fare-fetch attempt."""

    route: str
    flight_date: date
    price: Optional[int] = None
    success: bool
    error: Optional[str] = None


class PriceDrop(BaseModel):
    """A detected price drop that should trigger an instant alert."""

    route: str
    flight_date: date
    old_price: int
    new_price: int

    @property
    def drop_amount(self) -> int:
        return self.old_price - self.new_price


class WeeklySummaryItem(BaseModel):
    """Cheapest fare found for a route during the past week."""

    route: str
    cheapest_price: int
    cheapest_date: date
    samples_count: int
