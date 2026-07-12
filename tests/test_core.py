from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from database import TripDatabase
from models import TripInput, compute_trip_metrics


def make_trip() -> TripInput:
    """Create a deterministic valid trip for tests.

    Returns:
        A trip covering 40 km at 7 L/100 km and 1.80 €/L.
    """
    return TripInput(
        trip_date=date(2026, 7, 11),
        distance_km=40.0,
        avg_speed_kmh=80.0,
        avg_consumption_l_per_100km=7.0,
        fuel_price_eur_per_l=1.80,
        notes="Test trip",
    )


def test_compute_trip_metrics() -> None:
    """Verify all derived values for a representative trip."""
    metrics = compute_trip_metrics(make_trip())
    assert metrics.duration_hours == pytest.approx(0.5)
    assert metrics.fuel_used_l == pytest.approx(2.8)
    assert metrics.trip_cost_eur == pytest.approx(5.04)
    assert metrics.cost_per_100km_eur == pytest.approx(12.6)


def test_database_crud(tmp_path: Path) -> None:
    """Verify insertion, update, retrieval, and deletion."""
    database = TripDatabase(tmp_path / "test.db")
    trip_id = database.insert_trip(make_trip())

    stored = database.fetch_trip(trip_id)
    assert stored is not None
    assert stored["fuel_used_l"] == pytest.approx(2.8)
    assert stored["trip_cost_eur"] == pytest.approx(5.04)

    updated = TripInput(
        trip_date=date(2026, 7, 12),
        distance_km=100.0,
        avg_speed_kmh=100.0,
        avg_consumption_l_per_100km=6.0,
        fuel_price_eur_per_l=2.0,
    )
    database.update_trip(trip_id, updated)
    stored = database.fetch_trip(trip_id)
    assert stored is not None
    assert stored["fuel_used_l"] == pytest.approx(6.0)
    assert stored["trip_cost_eur"] == pytest.approx(12.0)

    database.delete_trip(trip_id)
    assert database.fetch_trip(trip_id) is None
