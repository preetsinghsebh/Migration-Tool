# Oracle to PostgreSQL Migration Tool

This is a production-style enterprise data migration tool built in Python.

## Structure

* `config/`: Configuration and settings (environment variables, logging setups).
* `connectors/`: Database connection management classes.
* `extractors/`: Modules for reading/extracting data from the source database.
* `converters/`: Modules for data transformation and mapping logic.
* `validators/`: Verification steps pre and post migration.
* `reports/`: Generation of audit reports.
* `logs/`: Application execution logs.
* `output/`: Any local file storage required during migration (e.g., CSV dumps).
* `tests/`: End-to-end and module-specific tests.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your DB credentials.
4. Run the connection test:
   ```bash
   python tests/test_connections.py
   ```
