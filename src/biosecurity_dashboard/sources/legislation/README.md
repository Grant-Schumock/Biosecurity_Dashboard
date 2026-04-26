# Legislation Sources

Use this folder for bills and policy data related to biosecurity, biodefense, pandemic preparedness, biosafety, and related topics.

Potential examples include Congress.gov, GovInfo, state legislatures, committee pages, or trusted policy trackers.

## Congress.gov

The ingestion script uses Congress.gov bill and summary endpoints, reads the API key from `CONGRESS_API_KEY`, and stores matched bills in the local SQLite database at `Data/processed/legislation.sqlite`.

```powershell
$env:PYTHONPATH = "src"
python scripts/ingest_congress.py
```

By default it inspects the 1000 most recently updated Congress.gov bills, fetches bill details, CRS summaries, and best-effort full text for each, then stores locally matched records for the dashboard to read.

## Regulations.gov

The Regulations.gov ingestion script reads the API key from `REGULATIONS_API_KEY`, searches the v4 document endpoint, and stores matched documents in the same local SQLite database.

```powershell
$env:PYTHONPATH = "src"
python scripts/ingest_regulations.py
```

By default it searches documents posted from 2015-01-01 through today and matches against document title, abstract, subject, document type, and agency metadata.

## FederalRegister.gov

FederalRegister.gov does not require an API key. The ingestion script searches the v1 document endpoint and stores matched documents in the same local SQLite database.

```powershell
$env:PYTHONPATH = "src"
python scripts/ingest_federal_register.py
```

By default it searches documents published from 2015-01-01 through today and matches against title, abstract, excerpts, action text, document type, agency names, topics, and docket ID.
