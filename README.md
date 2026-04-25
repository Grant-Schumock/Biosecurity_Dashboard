# Biosecurity_Dashboard
A unified biosecurity dashboard pulling from surveillance, publication, and policy feeds.

## Project layout

- `src/biosecurity_dashboard/` - Python package for the application.
- `src/biosecurity_dashboard/dashboard/` - dashboard UI code and button-triggered refresh flows.
- `src/biosecurity_dashboard/ingestion/` - shared data pull orchestration.
- `src/biosecurity_dashboard/sources/` - source-specific connectors for surveillance, legislation, and publications.
- `src/biosecurity_dashboard/storage/` - local storage helpers and schemas.
- `configs/` - source configuration and dashboard settings.
- `Data/` - local data files, kept out of git except documentation/placeholders.
- `scripts/` - command-line utilities for development and manual data refreshes.
- `tests/` - automated tests.

## Front end note

Python can work well end to end here. For a fast dashboard with button-triggered data pulls, good first options are Streamlit, Dash, or Panel. Streamlit is usually the quickest prototype; Dash gives more app-like control if the dashboard grows.

## Run The Dashboard

```powershell
$env:PYTHONPATH = "src"
streamlit run src/biosecurity_dashboard/dashboard/app.py
```
