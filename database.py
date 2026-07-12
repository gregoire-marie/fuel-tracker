from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from models import TripInput, TripMetrics, compute_trip_metrics


SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_date TEXT NOT NULL,
    distance_km REAL NOT NULL CHECK (distance_km > 0),
    avg_speed_kmh REAL NOT NULL CHECK (avg_speed_kmh > 0),
    avg_consumption_l_per_100km REAL NOT NULL
        CHECK (avg_consumption_l_per_100km > 0),
    fuel_price_eur_per_l REAL NOT NULL CHECK (fuel_price_eur_per_l > 0),
    duration_hours REAL NOT NULL CHECK (duration_hours > 0),
    fuel_used_l REAL NOT NULL CHECK (fuel_used_l > 0),
    trip_cost_eur REAL NOT NULL CHECK (trip_cost_eur > 0),
    cost_per_100km_eur REAL NOT NULL CHECK (cost_per_100km_eur > 0),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trips_trip_date ON trips (trip_date);
"""


class TripDatabase:
    """Provide a small SQLite repository for fuel-trip records."""

    def __init__(self, database_path: Path) -> None:
        """Initialize the repository and create its schema if needed.

        Args:
            database_path: Location of the SQLite database file.
        """
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a configured SQLite connection.

        Yields:
            An SQLite connection with row access by column name.
        """
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create database objects required by the application."""
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def insert_trip(self, trip: TripInput) -> int:
        """Insert a trip and its computed metrics.

        Args:
            trip: User-provided trip values.

        Returns:
            Identifier of the inserted trip.
        """
        metrics = compute_trip_metrics(trip)
        now = datetime.now().isoformat(timespec="seconds")
        values = self._serialize_trip(trip, metrics, now)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO trips (
                    trip_date,
                    distance_km,
                    avg_speed_kmh,
                    avg_consumption_l_per_100km,
                    fuel_price_eur_per_l,
                    duration_hours,
                    fuel_used_l,
                    trip_cost_eur,
                    cost_per_100km_eur,
                    notes,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            return int(cursor.lastrowid)

    def update_trip(self, trip_id: int, trip: TripInput) -> None:
        """Update a trip and recompute all derived values.

        Args:
            trip_id: Identifier of the record to update.
            trip: Replacement trip input values.

        Raises:
            KeyError: If no trip exists with the supplied identifier.
        """
        metrics = compute_trip_metrics(trip)
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE trips
                SET trip_date = ?,
                    distance_km = ?,
                    avg_speed_kmh = ?,
                    avg_consumption_l_per_100km = ?,
                    fuel_price_eur_per_l = ?,
                    duration_hours = ?,
                    fuel_used_l = ?,
                    trip_cost_eur = ?,
                    cost_per_100km_eur = ?,
                    notes = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    trip.trip_date.isoformat(),
                    trip.distance_km,
                    trip.avg_speed_kmh,
                    trip.avg_consumption_l_per_100km,
                    trip.fuel_price_eur_per_l,
                    metrics.duration_hours,
                    metrics.fuel_used_l,
                    metrics.trip_cost_eur,
                    metrics.cost_per_100km_eur,
                    trip.notes.strip(),
                    now,
                    trip_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Trip {trip_id} does not exist.")

    def delete_trip(self, trip_id: int) -> None:
        """Delete one trip.

        Args:
            trip_id: Identifier of the trip to delete.

        Raises:
            KeyError: If no trip exists with the supplied identifier.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM trips WHERE id = ?", (trip_id,)
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Trip {trip_id} does not exist.")

    def reset(self) -> int:
        """Delete every trip and restart the trip identifier sequence.

        Returns:
            Number of deleted trip records.
        """
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM trips")
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name = ?", ("trips",)
            )
            return int(cursor.rowcount)

    def fetch_trip(self, trip_id: int) -> dict[str, Any] | None:
        """Fetch one trip by identifier.

        Args:
            trip_id: Identifier of the requested trip.

        Returns:
            A record dictionary, or None when no record exists.
        """
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM trips WHERE id = ?", (trip_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def fetch_trips(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Load trips into a DataFrame, optionally constrained by date.

        Args:
            start_date: Inclusive lower date bound.
            end_date: Inclusive upper date bound.

        Returns:
            Trips sorted chronologically, with parsed date columns.
        """
        clauses: list[str] = []
        parameters: list[str] = []
        if start_date is not None:
            clauses.append("trip_date >= ?")
            parameters.append(start_date.isoformat())
        if end_date is not None:
            clauses.append("trip_date <= ?")
            parameters.append(end_date.isoformat())

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT *
            FROM trips
            {where_clause}
            ORDER BY trip_date ASC, id ASC
        """
        with self.connect() as connection:
            dataframe = pd.read_sql_query(query, connection, params=parameters)

        if dataframe.empty:
            return dataframe
        dataframe["trip_date"] = pd.to_datetime(dataframe["trip_date"])
        dataframe["created_at"] = pd.to_datetime(dataframe["created_at"])
        dataframe["updated_at"] = pd.to_datetime(dataframe["updated_at"])
        return dataframe

    def insert_demo_data(self) -> int:
        """Insert deterministic demonstration records.

        Returns:
            Number of inserted trips.
        """
        today = date.today()
        demo_rows = [
            (35, 42, 7.8, 1.78),
            (18, 28, 8.9, 1.78),
            (110, 104, 6.2, 1.81),
            (62, 76, 6.7, 1.81),
            (9, 21, 10.5, 1.81),
            (145, 112, 6.5, 1.84),
            (48, 61, 7.1, 1.84),
            (230, 118, 6.8, 1.86),
            (27, 35, 8.2, 1.86),
            (84, 88, 6.4, 1.83),
            (16, 25, 9.6, 1.83),
            (125, 108, 6.3, 1.80),
        ]
        for index, (distance, speed, consumption, price) in enumerate(demo_rows):
            self.insert_trip(
                TripInput(
                    trip_date=today - timedelta(days=(len(demo_rows) - index) * 5),
                    distance_km=float(distance),
                    avg_speed_kmh=float(speed),
                    avg_consumption_l_per_100km=float(consumption),
                    fuel_price_eur_per_l=float(price),
                    notes="Demonstration trip",
                )
            )
        return len(demo_rows)

    @staticmethod
    def _serialize_trip(
        trip: TripInput,
        metrics: TripMetrics,
        timestamp: str,
    ) -> tuple[Any, ...]:
        """Serialize domain objects for an INSERT statement.

        Args:
            trip: Source input record.
            metrics: Computed metrics for the trip.
            timestamp: Creation and update timestamp.

        Returns:
            Values ordered according to the INSERT statement.
        """
        return (
            trip.trip_date.isoformat(),
            trip.distance_km,
            trip.avg_speed_kmh,
            trip.avg_consumption_l_per_100km,
            trip.fuel_price_eur_per_l,
            metrics.duration_hours,
            metrics.fuel_used_l,
            metrics.trip_cost_eur,
            metrics.cost_per_100km_eur,
            trip.notes.strip(),
            timestamp,
            timestamp,
        )
