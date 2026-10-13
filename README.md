# Mini order synchronizer

A small Flask service for the OOOBS test task.

## Endpoints

- `GET /` — health check.
- `GET /result` — fetches orders from `https://test.ooobs.ru/api/orders`, normalizes Russian phone numbers, drops invalid phones, and merges duplicates.

For duplicate phone numbers, the record with the greatest `amount` is kept. If amounts are equal, the record with the latest `created_at` is kept.

The JSON response contains `clients` and `stats` (`received`, `unique`, `duplicates_merged`, `invalid_dropped`).

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

For production, run:

```bash
gunicorn app:app
```

The service reads the port from the `PORT` environment variable. No API keys or secrets are embedded in the source.
