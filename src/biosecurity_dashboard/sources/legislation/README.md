# Legislation Sources

Use this folder for bills and policy data related to biosecurity, biodefense, pandemic preparedness, biosafety, and related topics.

Potential examples include Congress.gov, GovInfo, state legislatures, committee pages, or trusted policy trackers.

## Congress.gov

The first ingestion script uses the Congress.gov v3 bill endpoint and reads the API key from `CONGRESS_API_KEY`.

```powershell
$env:PYTHONPATH = "src"
python scripts/ingest_congress.py
```

By default it fetches recent bills from the 119th Congress, filters list-level records for initial biosecurity/biodefense keywords, and writes a timestamped raw JSON file to `Data/raw/legislation/congress/`.
