# Fuel Trip Tracker

A local Streamlit app that helps:
- Store car trips,
- Visualize your consumption,
- Find the most economical speed for your daily commute.

## Demo

![Fuel Trip Tracker demo](docs/assets/demo.gif)

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\activate
```

The SQLite database is created automatically as `fuel_trips.db` in the project directory.
Set the `FUEL_TRACKER_DB` environment variable to use another location:

```bash
FUEL_TRACKER_DB=/path/to/trips.db streamlit run app.py
```

## Database schema

Each trip stores the entered date, distance, average speed, average consumption,
approximate fuel price, and notes. It also stores the derived duration, fuel used,
trip cost, and cost per 100 km. Derived values are recomputed when a trip is edited.

## Interpretation warning

The speed-consumption plots are observational. Average speed is correlated with route
type, traffic, gradients, weather, vehicle load, tire pressure, and driving style. The
quadratic fit and speed-band summaries should not be interpreted as causal estimates.

The dashboard includes:

- Aggregate distance, fuel, cost, consumption, price, and driving-time metrics
- Average speed versus consumption scatter plot with a quadratic descriptive fit
- Consumption history and five-trip moving average
- Cumulative fuel spending
- Monthly cost totals
- Distance-weighted consumption by speed band
- Speed-band and trip-length heatmap
- Date filtering and CSV export
- Record editing and deletion