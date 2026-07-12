from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics import (
    add_analysis_columns,
    aggregate_by_speed_band,
    fit_consumption_curve,
    summarize_trips,
)
from database import TripDatabase
from models import TripInput, compute_trip_metrics


APP_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(
    os.environ.get("FUEL_TRACKER_DB", APP_DIR / "fuel_trips.db")
)


@st.cache_resource
def get_database() -> TripDatabase:
    """Return the process-wide database repository.

    Returns:
        Initialized SQLite trip repository.
    """
    return TripDatabase(DATABASE_PATH)


def format_duration(hours: float) -> str:
    """Format a duration expressed in fractional hours.

    Args:
        hours: Duration in hours.

    Returns:
        Human-readable hour and minute representation.
    """
    total_minutes = int(round(hours * 60.0))
    display_hours, minutes = divmod(total_minutes, 60)
    return f"{display_hours} h {minutes:02d} min"


def build_trip_input(
    trip_date: date,
    distance_km: float,
    avg_speed_kmh: float,
    avg_consumption_l_per_100km: float,
    fuel_price_eur_per_l: float,
    notes: str,
) -> TripInput:
    """Construct a validated TripInput from form values.

    Args:
        trip_date: Date selected in the form.
        distance_km: Entered trip distance.
        avg_speed_kmh: Entered average speed.
        avg_consumption_l_per_100km: Entered average consumption.
        fuel_price_eur_per_l: Entered approximate fuel price.
        notes: Optional notes.

    Returns:
        Validated trip domain object.
    """
    trip = TripInput(
        trip_date=trip_date,
        distance_km=float(distance_km),
        avg_speed_kmh=float(avg_speed_kmh),
        avg_consumption_l_per_100km=float(avg_consumption_l_per_100km),
        fuel_price_eur_per_l=float(fuel_price_eur_per_l),
        notes=notes,
    )
    trip.validate()
    return trip


def save_trip_from_form(database: TripDatabase) -> None:
    """Persist the values submitted by the new-trip form.

    Args:
        database: Trip repository receiving the submitted record.
    """
    trip = build_trip_input(
        st.session_state["new_trip_date"],
        st.session_state["new_trip_distance_km"],
        st.session_state["new_trip_avg_speed_kmh"],
        st.session_state["new_trip_avg_consumption"],
        st.session_state["new_trip_fuel_price"],
        st.session_state["new_trip_notes"],
    )
    trip_id = database.insert_trip(trip)
    st.session_state["trip_save_message"] = f"Trip #{trip_id} saved."


def render_trip_form(database: TripDatabase) -> None:
    """Render the trip-entry form and persist submitted records.

    Args:
        database: Trip repository receiving submitted records.
    """
    st.subheader("Add a trip")
    with st.form("new_trip", clear_on_submit=True):
        first, second = st.columns(2)
        with first:
            trip_date = st.date_input(
                "Trip date", value=date.today(), key="new_trip_date"
            )
            distance_km = st.number_input(
                "Length [km]",
                min_value=0.1,
                value=40.0,
                step=1.0,
                key="new_trip_distance_km",
            )
            avg_speed_kmh = st.number_input(
                "Average speed [km/h]",
                min_value=0.1,
                value=70.0,
                step=1.0,
                key="new_trip_avg_speed_kmh",
            )
        with second:
            avg_consumption = st.number_input(
                "Average consumption [L/100 km]",
                min_value=0.1,
                value=7.0,
                step=0.1,
                key="new_trip_avg_consumption",
            )
            fuel_price = st.number_input(
                "Approximate fuel price [€/L]",
                min_value=0.01,
                value=1.80,
                step=0.01,
                format="%.3f",
                key="new_trip_fuel_price",
            )
            notes = st.text_input(
                "Notes", placeholder="Optional", key="new_trip_notes"
            )

        preview = build_trip_input(
            trip_date,
            distance_km,
            avg_speed_kmh,
            avg_consumption,
            fuel_price,
            notes,
        )
        metrics = compute_trip_metrics(preview)
        metric_columns = st.columns(4)
        metric_columns[0].metric("Fuel used", f"{metrics.fuel_used_l:.2f} L")
        metric_columns[1].metric("Trip cost", f"{metrics.trip_cost_eur:.2f} €")
        metric_columns[2].metric(
            "Cost per 100 km", f"{metrics.cost_per_100km_eur:.2f} €"
        )
        metric_columns[3].metric(
            "Estimated duration", format_duration(metrics.duration_hours)
        )

        st.form_submit_button(
            "Save trip",
            type="primary",
            on_click=save_trip_from_form,
            args=(database,),
        )

    if save_message := st.session_state.pop("trip_save_message", None):
        st.success(save_message)


def render_summary_cards(dataframe: pd.DataFrame) -> None:
    """Render top-level aggregate metrics.

    Args:
        dataframe: Filtered trip records.
    """
    summary = summarize_trips(dataframe)
    first_row = st.columns(4)
    first_row[0].metric("Trips", f"{summary.trip_count}")
    first_row[1].metric("Distance", f"{summary.total_distance_km:,.0f} km")
    first_row[2].metric("Fuel used", f"{summary.total_fuel_l:,.1f} L")
    first_row[3].metric("Fuel cost", f"{summary.total_cost_eur:,.2f} €")

    second_row = st.columns(4)
    second_row[0].metric(
        "Weighted consumption",
        f"{summary.weighted_consumption_l_per_100km:.2f} L/100 km",
    )
    second_row[1].metric(
        "Weighted fuel price", f"{summary.weighted_fuel_price_eur_per_l:.3f} €/L"
    )
    second_row[2].metric(
        "Cost per 100 km", f"{summary.cost_per_100km_eur:.2f} €"
    )
    second_row[3].metric(
        "Driving time", format_duration(summary.total_duration_hours)
    )


def render_speed_consumption_chart(dataframe: pd.DataFrame) -> None:
    """Render the main speed-versus-consumption relationship chart.

    Args:
        dataframe: Enriched trip records.
    """
    figure = px.scatter(
        dataframe,
        x="avg_speed_kmh",
        y="avg_consumption_l_per_100km",
        size="distance_km",
        color="cost_per_100km_eur",
        hover_data={
            "trip_date": "|%Y-%m-%d",
            "distance_km": ":.1f",
            "avg_speed_kmh": ":.1f",
            "avg_consumption_l_per_100km": ":.2f",
            "cost_per_100km_eur": ":.2f",
            "trip_cost_eur": ":.2f",
        },
        labels={
            "avg_speed_kmh": "Average speed [km/h]",
            "avg_consumption_l_per_100km": "Consumption [L/100 km]",
            "distance_km": "Distance [km]",
            "cost_per_100km_eur": "Cost [€/100 km]",
        },
        title="Consumption as a function of average speed",
    )
    fitted_curve = fit_consumption_curve(dataframe)
    if not fitted_curve.empty:
        figure.add_trace(
            go.Scatter(
                x=fitted_curve["avg_speed_kmh"],
                y=fitted_curve["fitted_consumption_l_per_100km"],
                mode="lines",
                name="Quadratic fit",
            )
        )
    figure.update_layout(legend_title_text="")
    st.plotly_chart(figure, width="stretch")


def render_time_series(dataframe: pd.DataFrame) -> None:
    """Render chronological consumption and cumulative-cost charts.

    Args:
        dataframe: Enriched trip records sorted chronologically.
    """
    consumption_figure = go.Figure()
    consumption_figure.add_trace(
        go.Scatter(
            x=dataframe["trip_date"],
            y=dataframe["avg_consumption_l_per_100km"],
            mode="lines+markers",
            name="Trip consumption",
        )
    )
    consumption_figure.add_trace(
        go.Scatter(
            x=dataframe["trip_date"],
            y=dataframe["rolling_consumption_l_per_100km"],
            mode="lines",
            name="5-trip moving average",
        )
    )
    consumption_figure.update_layout(
        title="Consumption over time",
        xaxis_title="Trip date",
        yaxis_title="Consumption [L/100 km]",
    )

    cumulative_figure = px.area(
        dataframe,
        x="trip_date",
        y="cumulative_cost_eur",
        labels={
            "trip_date": "Trip date",
            "cumulative_cost_eur": "Cumulative fuel cost [€]",
        },
        title="Cumulative fuel spending",
    )

    left, right = st.columns(2)
    left.plotly_chart(consumption_figure, width="stretch")
    right.plotly_chart(cumulative_figure, width="stretch")


def render_grouped_statistics(dataframe: pd.DataFrame) -> None:
    """Render grouped speed-band and monthly statistics.

    Args:
        dataframe: Enriched trip records.
    """
    speed_summary = aggregate_by_speed_band(dataframe)
    monthly = (
        dataframe.groupby("month", as_index=False)
        .agg(
            distance_km=("distance_km", "sum"),
            trip_cost_eur=("trip_cost_eur", "sum"),
            fuel_used_l=("fuel_used_l", "sum"),
        )
        .sort_values("month")
    )

    speed_figure = px.bar(
        speed_summary,
        x="speed_band",
        y="weighted_consumption_l_per_100km",
        text_auto=".2f",
        hover_data={"trip_count": True, "distance_km": ":.1f"},
        labels={
            "speed_band": "Average-speed band [km/h]",
            "weighted_consumption_l_per_100km": "Weighted consumption [L/100 km]",
            "trip_count": "Trips",
            "distance_km": "Distance [km]",
        },
        title="Distance-weighted consumption by speed band",
    )
    monthly_figure = px.bar(
        monthly,
        x="month",
        y="trip_cost_eur",
        hover_data={"distance_km": ":.1f", "fuel_used_l": ":.2f"},
        labels={
            "month": "Month",
            "trip_cost_eur": "Fuel cost [€]",
            "distance_km": "Distance [km]",
            "fuel_used_l": "Fuel used [L]",
        },
        title="Monthly fuel cost",
    )

    left, right = st.columns(2)
    left.plotly_chart(speed_figure, width="stretch")
    right.plotly_chart(monthly_figure, width="stretch")

    eligible = speed_summary[speed_summary["trip_count"] >= 3]
    if not eligible.empty:
        best = eligible.loc[
            eligible["weighted_consumption_l_per_100km"].idxmin()
        ]
        st.info(
            "Most efficient observed speed band with at least three trips: "
            f"{best['speed_band']} km/h at "
            f"{best['weighted_consumption_l_per_100km']:.2f} L/100 km. "
            "This is descriptive, not causal: route, traffic, elevation, weather, "
            "load, and driving style are not controlled."
        )


def render_heatmap(dataframe: pd.DataFrame) -> None:
    """Render mean consumption across speed and distance bands.

    Args:
        dataframe: Enriched trip records containing categorical bands.
    """
    pivot = dataframe.pivot_table(
        index="distance_band",
        columns="speed_band",
        values="avg_consumption_l_per_100km",
        aggfunc="mean",
        observed=True,
    )
    if pivot.empty:
        return
    figure = go.Figure(
        data=go.Heatmap(
            z=pivot.to_numpy(),
            x=[str(value) for value in pivot.columns],
            y=[str(value) for value in pivot.index],
            colorbar={"title": "L/100 km"},
            hovertemplate=(
                "Speed: %{x} km/h<br>Distance: %{y} km"
                "<br>Mean consumption: %{z:.2f} L/100 km<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        title="Mean consumption heatmap",
        xaxis_title="Average-speed band [km/h]",
        yaxis_title="Trip-length band [km]",
    )
    st.plotly_chart(figure, width="stretch")


def render_dashboard(dataframe: pd.DataFrame) -> None:
    """Render all analytical views for the selected trip subset.

    Args:
        dataframe: Filtered trip records.
    """
    if dataframe.empty:
        st.warning("No trips match the selected period.")
        return
    enriched = add_analysis_columns(dataframe)
    render_summary_cards(enriched)
    st.divider()
    render_speed_consumption_chart(enriched)
    render_time_series(enriched)
    render_grouped_statistics(enriched)
    render_heatmap(enriched)


def render_trip_log(database: TripDatabase, dataframe: pd.DataFrame) -> None:
    """Render the trip table, export, edit, and delete controls.

    Args:
        database: Trip repository used for write operations.
        dataframe: Complete trip history.
    """
    st.subheader("Trip log")
    if dataframe.empty:
        st.info("No trips have been recorded.")
        return

    display_columns = {
        "id": "ID",
        "trip_date": "Date",
        "distance_km": "Distance [km]",
        "avg_speed_kmh": "Avg speed [km/h]",
        "avg_consumption_l_per_100km": "Consumption [L/100 km]",
        "fuel_price_eur_per_l": "Fuel price [€/L]",
        "fuel_used_l": "Fuel used [L]",
        "trip_cost_eur": "Trip cost [€]",
        "cost_per_100km_eur": "Cost [€/100 km]",
        "duration_hours": "Duration [h]",
        "notes": "Notes",
    }
    table = dataframe[list(display_columns)].rename(columns=display_columns)
    # Render this table as sanitized HTML below instead of using Streamlit's
    # PyArrow IPC path, which segfaults on reruns with Python 3.14 on macOS.
    table["Date"] = table["Date"].dt.strftime("%Y-%m-%d")
    table = table.sort_values(["Date", "ID"], ascending=False)
    table_html = table.to_html(
        index=False,
        border=0,
        escape=True,
        classes="trip-log-table",
        justify="left",
        formatters={
            "Distance [km]": lambda value: f"{value:.1f}",
            "Avg speed [km/h]": lambda value: f"{value:.1f}",
            "Consumption [L/100 km]": lambda value: f"{value:.2f}",
            "Fuel price [€/L]": lambda value: f"{value:.3f}",
            "Fuel used [L]": lambda value: f"{value:.2f}",
            "Trip cost [€]": lambda value: f"{value:.2f}",
            "Cost [€/100 km]": lambda value: f"{value:.2f}",
            "Duration [h]": lambda value: f"{value:.2f}",
        },
    )
    is_dark = st.context.theme.type == "dark"
    colors = {
        "surface": "#111827" if is_dark else "#ffffff",
        "header": "#1f2937" if is_dark else "#f8fafc",
        "stripe": "#172033" if is_dark else "#f8fafc",
        "hover": "#1e3a5f" if is_dark else "#eff6ff",
        "border": "#374151" if is_dark else "#e2e8f0",
        "text": "#e5e7eb" if is_dark else "#1e293b",
        "muted": "#9ca3af" if is_dark else "#64748b",
        "accent": "#60a5fa" if is_dark else "#2563eb",
        "shadow": "rgba(0, 0, 0, 0.28)" if is_dark else "rgba(15, 23, 42, 0.08)",
    }
    styled_table = f"""
        <style>
            .trip-log-shell {{
                max-height: 34rem;
                overflow: auto;
                overscroll-behavior: contain;
                border: 1px solid {colors["border"]};
                border-radius: 0.75rem;
                background: {colors["surface"]};
                box-shadow: 0 1px 2px {colors["shadow"]};
            }}
            .trip-log-table {{
                width: 100%;
                min-width: 72rem;
                border-collapse: separate;
                border-spacing: 0;
                color: {colors["text"]};
                font-size: 0.875rem;
                line-height: 1.35;
            }}
            .trip-log-table thead th {{
                position: sticky;
                top: 0;
                z-index: 1;
                padding: 0.75rem 0.875rem;
                border-bottom: 1px solid {colors["border"]};
                background: {colors["header"]};
                color: {colors["muted"]};
                font-size: 0.75rem;
                font-weight: 650;
                letter-spacing: 0.025em;
                text-align: left;
                text-transform: uppercase;
                white-space: nowrap;
            }}
            .trip-log-table tbody td {{
                padding: 0.72rem 0.875rem;
                border-bottom: 1px solid {colors["border"]};
                background: {colors["surface"]};
                vertical-align: middle;
                white-space: nowrap;
            }}
            .trip-log-table tbody tr:nth-child(even) td {{
                background: {colors["stripe"]};
            }}
            .trip-log-table tbody tr:hover td {{
                background: {colors["hover"]};
            }}
            .trip-log-table tbody tr:last-child td {{
                border-bottom: 0;
            }}
            .trip-log-table th:nth-child(1),
            .trip-log-table th:nth-child(n+3):nth-child(-n+10),
            .trip-log-table td:nth-child(1),
            .trip-log-table td:nth-child(n+3):nth-child(-n+10) {{
                text-align: right;
                font-variant-numeric: tabular-nums;
            }}
            .trip-log-table td:first-child {{
                color: {colors["accent"]};
                font-weight: 650;
            }}
            .trip-log-table td:nth-child(2) {{
                font-weight: 550;
            }}
            .trip-log-table th:last-child,
            .trip-log-table td:last-child {{
                min-width: 14rem;
                white-space: normal;
            }}
        </style>
        <div class="trip-log-shell">{table_html}</div>
    """
    trip_label = "trip" if len(table) == 1 else "trips"
    st.caption(f"{len(table)} {trip_label} · newest first")
    st.html(styled_table)

    csv_bytes = dataframe.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Export all trips as CSV",
        data=csv_bytes,
        file_name="fuel_trips.csv",
        mime="text/csv",
    )

    st.divider()
    st.subheader("Edit or delete a trip")
    trip_ids = dataframe["id"].astype(int).tolist()
    selected_id = st.selectbox("Trip ID", options=trip_ids)
    record = database.fetch_trip(int(selected_id))
    if record is None:
        st.error("The selected trip no longer exists.")
        return

    with st.form("edit_trip"):
        first, second = st.columns(2)
        with first:
            edited_date = st.date_input(
                "Date", value=date.fromisoformat(str(record["trip_date"]))
            )
            edited_distance = st.number_input(
                "Length [km]", min_value=0.1, value=float(record["distance_km"])
            )
            edited_speed = st.number_input(
                "Average speed [km/h]",
                min_value=0.1,
                value=float(record["avg_speed_kmh"]),
            )
        with second:
            edited_consumption = st.number_input(
                "Average consumption [L/100 km]",
                min_value=0.1,
                value=float(record["avg_consumption_l_per_100km"]),
            )
            edited_price = st.number_input(
                "Approximate fuel price [€/L]",
                min_value=0.01,
                value=float(record["fuel_price_eur_per_l"]),
                format="%.3f",
            )
            edited_notes = st.text_input("Notes", value=str(record["notes"]))

        save_changes = st.form_submit_button("Save changes", type="primary")
        if save_changes:
            updated_trip = build_trip_input(
                edited_date,
                edited_distance,
                edited_speed,
                edited_consumption,
                edited_price,
                edited_notes,
            )
            database.update_trip(int(selected_id), updated_trip)
            st.success(f"Trip #{selected_id} updated.")
            st.rerun()

    with st.form("delete_trip"):
        confirm_delete = st.checkbox(
            f"I confirm that trip #{selected_id} should be deleted."
        )
        delete_trip = st.form_submit_button("Delete selected trip")

    if delete_trip:
        if not confirm_delete:
            st.warning("Confirm the deletion before deleting the trip.")
        else:
            database.delete_trip(int(selected_id))
            st.success(f"Trip #{selected_id} deleted.")
            st.rerun()


def render_sidebar_filters(dataframe: pd.DataFrame) -> tuple[date | None, date | None]:
    """Render dashboard date filters.

    Args:
        dataframe: Complete trip history.

    Returns:
        Inclusive start and end dates, or two None values for empty data.
    """
    st.sidebar.header("Dashboard filters")
    if dataframe.empty:
        return None, None
    minimum_date = dataframe["trip_date"].min().date()
    maximum_date = dataframe["trip_date"].max().date()
    selected_range = st.sidebar.date_input(
        "Trip period",
        value=(minimum_date, maximum_date),
        min_value=minimum_date,
        max_value=maximum_date,
    )
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        return selected_range[0], selected_range[1]
    return minimum_date, maximum_date


def main() -> None:
    """Run the Streamlit fuel-trip tracking application."""
    st.set_page_config(
        page_title="Fuel Trip Tracker",
        page_icon=None,
        layout="wide",
    )
    st.title("Fuel Trip Tracker")
    st.caption(
        "Store trip measurements, estimate fuel use and cost, and analyse how "
        "consumption varies with driving conditions."
    )

    database = get_database()

    all_trips = database.fetch_trips()

    if all_trips.empty:
        st.sidebar.info("The database is empty.")
        if st.sidebar.button("Load demonstration data"):
            inserted = database.insert_demo_data()
            st.sidebar.success(f"Inserted {inserted} demonstration trips.")
            st.rerun()

    start_date, end_date = render_sidebar_filters(all_trips)
    filtered_trips = (
        database.fetch_trips(start_date, end_date)
        if start_date is not None and end_date is not None
        else all_trips
    )

    entry_tab, dashboard_tab, log_tab = st.tabs(
        ["Add trip", "Dashboard", "Trip log"]
    )
    with entry_tab:
        render_trip_form(database)
    with dashboard_tab:
        render_dashboard(filtered_trips)
    with log_tab:
        render_trip_log(database, all_trips)

    st.sidebar.divider()
    st.sidebar.caption(f"Database: {DATABASE_PATH}")


if __name__ == "__main__":
    main()
