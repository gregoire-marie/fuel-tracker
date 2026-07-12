from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

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


def run_app(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AppTest:
    """Run the Streamlit app against an isolated database."""
    monkeypatch.setenv("FUEL_TRACKER_DB", str(database_path))
    st.cache_resource.clear()
    app_path = Path(__file__).parents[1] / "app.py"
    return AppTest.from_file(str(app_path), default_timeout=15).run()


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


def test_trip_form_write_flows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify adding and deleting trips do not crash the Streamlit app."""
    database_path = tmp_path / "app.db"
    database = TripDatabase(database_path)
    trip_id = database.insert_trip(make_trip())
    app = run_app(database_path, monkeypatch)
    assert not app.exception

    save_button = next(
        button for button in app.button if button.label == "Save trip"
    )
    save_button.click().run()
    assert not app.exception
    assert len(database.fetch_trips()) == 2
    assert any("saved" in message.value for message in app.success)
    assert not app.dataframe
    trip_log_html = next(node.proto.body for node in app if node.type == "html")
    assert "trip-log-shell" in trip_log_html
    assert "position: sticky" in trip_log_html

    trip_selector = next(
        selectbox for selectbox in app.selectbox if selectbox.label == "Trip ID"
    )
    trip_selector.select(trip_selector.options[-1]).run()
    assert not app.exception

    trip_selector = next(
        selectbox for selectbox in app.selectbox if selectbox.label == "Trip ID"
    )
    trip_selector.select(str(trip_id)).run()
    assert not app.exception

    delete_button = next(
        button for button in app.button if button.label == "Delete selected trip"
    )
    delete_button.click().run()
    assert not app.exception
    assert database.fetch_trip(trip_id) is not None
    assert any("Confirm the deletion" in warning.value for warning in app.warning)

    confirmation = next(
        checkbox
        for checkbox in app.checkbox
        if checkbox.label.startswith("I confirm that trip #")
    )
    confirmation.check().run()
    assert not app.exception

    delete_button = next(
        button for button in app.button if button.label == "Delete selected trip"
    )
    delete_button.click().run()
    assert not app.exception
    assert database.fetch_trip(trip_id) is None


def test_database_reset(tmp_path: Path) -> None:
    """Verify reset clears all trips and restarts identifiers."""
    database = TripDatabase(tmp_path / "reset.db")
    database.insert_trip(make_trip())
    database.insert_trip(make_trip())

    assert database.reset() == 2
    assert database.fetch_trips().empty
    assert database.insert_trip(make_trip()) == 1


def test_database_reset_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the database reset requires explicit confirmation."""
    database_path = tmp_path / "reset-app.db"
    database = TripDatabase(database_path)
    database.insert_trip(make_trip())
    app = run_app(database_path, monkeypatch)

    reset_button = next(
        button for button in app.button if button.label == "Reset database"
    )
    reset_button.click().run()
    assert not app.exception
    assert len(database.fetch_trips()) == 1
    assert any("Confirm the reset" in warning.value for warning in app.warning)

    reset_confirmation = next(
        checkbox
        for checkbox in app.checkbox
        if checkbox.label.startswith("I understand that all trips")
    )
    reset_confirmation.check().run()
    reset_button = next(
        button for button in app.button if button.label == "Reset database"
    )
    reset_button.click().run()
    assert not app.exception
    assert database.fetch_trips().empty
    assert any("Database reset" in message.value for message in app.success)
    assert database.insert_trip(make_trip()) == 1


def test_operating_map_chart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the operating map identifies the lowest observed consumption."""
    database_path = tmp_path / "chart-app.db"
    database = TripDatabase(database_path)
    database.insert_trip(make_trip())
    database.insert_trip(
        TripInput(
            trip_date=date(2026, 7, 12),
            distance_km=110.0,
            avg_speed_kmh=104.0,
            avg_consumption_l_per_100km=6.2,
            fuel_price_eur_per_l=1.80,
        )
    )
    app = run_app(database_path, monkeypatch)

    plotly_specs = [
        json.loads(chart.proto.spec) for chart in app.get("plotly_chart")
    ]
    operating_map = next(
        spec
        for spec in plotly_specs
        if spec["layout"].get("title", {}).get("text")
        == "Observed operating map"
    )
    assert operating_map["data"][1]["marker"]["symbol"] == "star"
    assert not any(
        "Most efficient observed speed band" in info.value for info in app.info
    )
