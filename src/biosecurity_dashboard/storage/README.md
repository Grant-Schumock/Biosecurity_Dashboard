# Storage

SQLite persistence helpers for the local dashboard database.

Current local database:

- `Data/processed/legislation.sqlite`

Main tables:

- `bills` - matched Congress.gov bills.
- `regulatory_documents` - matched Regulations.gov documents.
- `federal_register_documents` - matched FederalRegister.gov documents.
- `refresh_metadata` - most recent refresh metadata by source.

Generated databases are ignored by git.
