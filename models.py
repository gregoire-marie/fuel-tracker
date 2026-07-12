from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class TripInput:
    """Represent user-provided trip measurements.

    Attributes:
        trip_date: Calendar date of the trip.
        distance_km: Distance travelled in kilometres.
        avg_speed_kmh: Average speed in kilometres per hour.
        avg_consumption_l_per_100km: Average fuel consumption in litres per 100 km.
        fuel_price_eur_per_l: Approximate purchase price of fuel in euros per litre.
        notes: Optional free-text notes.
    """

    trip_date: date
    distance_km: float
    avg_speed_kmh: float
    avg_consumption_l_per_100km: float
    fuel_price_eur_per_l: float
    notes: str = ""

    def validate(self) -> None:
        """Validate that all numeric trip values are physically meaningful.

        Raises:
            ValueError: If a required value is zero or negative.
        """
        positive_values = {
            "distance_km": self.distance_km,
            "avg_speed_kmh": self.avg_speed_kmh,
            "avg_consumption_l_per_100km": self.avg_consumption_l_per_100km,
            "fuel_price_eur_per_l": self.fuel_price_eur_per_l,
        }
        for field_name, value in positive_values.items():
            if value <= 0:
                raise ValueError(f"{field_name} must be strictly positive.")


@dataclass(frozen=True, slots=True)
class TripMetrics:
    """Represent values derived from one trip.

    Attributes:
        duration_hours: Estimated trip duration in hours.
        fuel_used_l: Estimated quantity of fuel used in litres.
        trip_cost_eur: Estimated trip fuel cost in euros.
        cost_per_100km_eur: Estimated fuel cost per 100 km in euros.
    """

    duration_hours: float
    fuel_used_l: float
    trip_cost_eur: float
    cost_per_100km_eur: float


def compute_trip_metrics(trip: TripInput) -> TripMetrics:
    """Compute derived fuel and cost metrics for a trip.

    Args:
        trip: Validated trip input values.

    Returns:
        Derived duration, fuel use, trip cost, and cost per 100 km.

    Raises:
        ValueError: If the trip contains an invalid numeric value.
    """
    trip.validate()
    duration_hours = trip.distance_km / trip.avg_speed_kmh
    fuel_used_l = (
        trip.distance_km * trip.avg_consumption_l_per_100km / 100.0
    )
    trip_cost_eur = fuel_used_l * trip.fuel_price_eur_per_l
    cost_per_100km_eur = (
        trip.avg_consumption_l_per_100km * trip.fuel_price_eur_per_l
    )
    return TripMetrics(
        duration_hours=duration_hours,
        fuel_used_l=fuel_used_l,
        trip_cost_eur=trip_cost_eur,
        cost_per_100km_eur=cost_per_100km_eur,
    )
