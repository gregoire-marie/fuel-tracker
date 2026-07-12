from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class SummaryMetrics:
    """Store aggregate statistics for a filtered collection of trips."""

    trip_count: int
    total_distance_km: float
    total_fuel_l: float
    total_cost_eur: float
    weighted_consumption_l_per_100km: float
    weighted_fuel_price_eur_per_l: float
    cost_per_100km_eur: float
    total_duration_hours: float


def summarize_trips(dataframe: pd.DataFrame) -> SummaryMetrics:
    """Compute distance- and fuel-weighted summary statistics.

    Args:
        dataframe: Trip records containing raw and derived fields.

    Returns:
        Aggregate metrics. Empty inputs yield zeros.
    """
    if dataframe.empty:
        return SummaryMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    total_distance = float(dataframe["distance_km"].sum())
    total_fuel = float(dataframe["fuel_used_l"].sum())
    total_cost = float(dataframe["trip_cost_eur"].sum())
    weighted_consumption = (
        100.0 * total_fuel / total_distance if total_distance > 0 else 0.0
    )
    weighted_fuel_price = (
        total_cost / total_fuel if total_fuel > 0 else 0.0
    )
    cost_per_100km = (
        100.0 * total_cost / total_distance if total_distance > 0 else 0.0
    )
    return SummaryMetrics(
        trip_count=int(len(dataframe)),
        total_distance_km=total_distance,
        total_fuel_l=total_fuel,
        total_cost_eur=total_cost,
        weighted_consumption_l_per_100km=weighted_consumption,
        weighted_fuel_price_eur_per_l=weighted_fuel_price,
        cost_per_100km_eur=cost_per_100km,
        total_duration_hours=float(dataframe["duration_hours"].sum()),
    )


def add_analysis_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add columns used by charts and grouped statistics.

    Args:
        dataframe: Raw trip DataFrame.

    Returns:
        A copied DataFrame with chronological and binned fields.
    """
    if dataframe.empty:
        return dataframe.copy()

    enriched = dataframe.copy().sort_values(["trip_date", "id"])
    enriched["cost_per_km_eur"] = (
        enriched["trip_cost_eur"] / enriched["distance_km"]
    )
    enriched["cumulative_cost_eur"] = enriched["trip_cost_eur"].cumsum()
    enriched["cumulative_distance_km"] = enriched["distance_km"].cumsum()
    enriched["rolling_consumption_l_per_100km"] = (
        enriched["avg_consumption_l_per_100km"].rolling(5, min_periods=1).mean()
    )
    enriched["month"] = enriched["trip_date"].dt.to_period("M").astype(str)
    enriched["speed_band"] = pd.cut(
        enriched["avg_speed_kmh"],
        bins=[0, 30, 50, 70, 90, 110, 130, np.inf],
        labels=["0–30", "30–50", "50–70", "70–90", "90–110", "110–130", "130+"],
        right=False,
    )
    enriched["distance_band"] = pd.cut(
        enriched["distance_km"],
        bins=[0, 10, 25, 50, 100, 200, np.inf],
        labels=["0–10", "10–25", "25–50", "50–100", "100–200", "200+"],
        right=False,
    )
    return enriched


def aggregate_by_speed_band(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Aggregate weighted consumption statistics by average-speed band.

    Args:
        dataframe: Enriched trip records containing a speed_band column.

    Returns:
        One row per populated speed band.
    """
    if dataframe.empty:
        return pd.DataFrame()

    grouped = dataframe.groupby("speed_band", observed=True, sort=True)
    rows: list[dict[str, float | int | str]] = []
    for speed_band, group in grouped:
        distance = float(group["distance_km"].sum())
        fuel = float(group["fuel_used_l"].sum())
        rows.append(
            {
                "speed_band": str(speed_band),
                "trip_count": int(len(group)),
                "distance_km": distance,
                "weighted_consumption_l_per_100km": (
                    100.0 * fuel / distance if distance > 0 else 0.0
                ),
                "mean_cost_per_100km_eur": float(
                    group["cost_per_100km_eur"].mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def fit_consumption_curve(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Fit a quadratic speed-consumption curve when enough data exists.

    Args:
        dataframe: Trip records with speed and consumption columns.

    Returns:
        Smooth fitted points, or an empty DataFrame if fitting is unsupported.
    """
    if len(dataframe) < 4 or dataframe["avg_speed_kmh"].nunique() < 3:
        return pd.DataFrame()

    x_values = dataframe["avg_speed_kmh"].to_numpy(dtype=float)
    y_values = dataframe["avg_consumption_l_per_100km"].to_numpy(dtype=float)
    coefficients = np.polyfit(x_values, y_values, deg=2)
    x_curve = np.linspace(float(x_values.min()), float(x_values.max()), 150)
    y_curve = np.polyval(coefficients, x_curve)
    return pd.DataFrame(
        {
            "avg_speed_kmh": x_curve,
            "fitted_consumption_l_per_100km": y_curve,
        }
    )
