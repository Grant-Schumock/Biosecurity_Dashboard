# Dashboard

Streamlit dashboard for local biosecurity policy records.

The dashboard reads from `Data/processed/legislation.sqlite` and includes:

- Sidebar controls for local keyword search, date range, source filters, sorting, and data refresh.
- Grouped rows for related records, using normalized docket numbers when available.
- Expanded source rows for the individual records behind each group.

## Run locally

```powershell
$env:PYTHONPATH = "src"
streamlit run src/biosecurity_dashboard/dashboard/app.py
```
