# Scripts

Command-line utilities for source ingestion and source-specific smoke tests.

## Ingestion

These scripts fetch matching records and upsert them into `Data/processed/legislation.sqlite`:

```powershell
$env:PYTHONPATH = "src"
python scripts/ingest_congress.py
python scripts/ingest_regulations.py
python scripts/ingest_federal_register.py
```

All ingestion scripts accept `--start-date`, `--end-date`, and repeated `--keyword` arguments. Congress.gov and Regulations.gov require API keys in `CONGRESS_API_KEY` and `REGULATIONS_API_KEY`.

## Source Checks

The `fetch_one_*` and `test_*_keyword.py` scripts are lightweight probes for inspecting one source record or testing keyword matching against a known record.
