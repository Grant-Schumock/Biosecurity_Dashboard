# Legislation Sources

API clients for policy data related to biosecurity, biodefense, pandemic preparedness, biosafety, and related topics.

All clients use the current keyword list from `congress.py` unless explicit `--keyword` values are passed to a script.

## Congress.gov

The Congress.gov client reads the API key from `CONGRESS_API_KEY`. The ingestion script filters the bill list by update date using `fromDateTime` and `toDateTime`, enriches candidate bills with details, summaries, and best-effort full text, then stores local keyword matches in `Data/processed/legislation.sqlite`.

```powershell
$env:PYTHONPATH = "src"
python scripts/ingest_congress.py --start-date 2026-01-01 --end-date 2026-04-26
```

Use `--max-api-calls` and `--max-bills` to cap larger runs.

## Regulations.gov

The Regulations.gov client reads the API key from `REGULATIONS_API_KEY`, searches the v4 document endpoint by keyword and posted date, enriches returned documents, and stores local keyword matches in the same SQLite database.

```powershell
$env:PYTHONPATH = "src"
python scripts/ingest_regulations.py --start-date 2026-01-01 --end-date 2026-04-26
```

Matching uses title, abstract, subject, document type, and agency metadata.

## FederalRegister.gov

FederalRegister.gov does not require an API key. The client searches the v1 document endpoint by keyword and publication date, downloads best-effort full text, and stores local keyword matches in the same SQLite database.

```powershell
$env:PYTHONPATH = "src"
python scripts/ingest_federal_register.py --start-date 2026-01-01 --end-date 2026-04-26
```

Matching uses title, abstract, excerpts, action text, full text, document type, agency names, topics, and docket ID.
