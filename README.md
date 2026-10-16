# Hospital Bulk Processing API

A FastAPI service that accepts a CSV of up to 20 hospital records and creates them through the existing Hospital Directory API.

## Architecture

- `app/main.py`: HTTP routes and upload limits.
- `app/csv_parser.py`: complete CSV validation before upstream side effects.
- `app/hospital_client.py`: HTTP adapter for the upstream API.
- `app/bulk_service.py`: sequential batch workflow, activation, and cleanup policy.
- `app/schemas.py`: request and response data models.

The upstream API remains the source of truth; this application does not maintain a separate hospital database.

## Run locally

Requires Python 3.10+ (the assignment asks for Python 3.8+, but this starter uses Pydantic v2 and is tested for modern Python).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs.

## Upload a CSV

```bash
curl -X POST http://127.0.0.1:8000/hospitals/bulk \
  -F 'file=@hospitals.csv'
```

CSV headers: `name,address,phone`. `name` and `address` are required; `phone` is optional. Maximum: 20 non-empty records.

## Failure semantics

- Invalid input returns HTTP 422 before upstream requests.
- Upstream processing failures return HTTP 502 with a structured result.
- Creation is sequential. On the first creation failure, later rows are not attempted and batch deletion is attempted.
- The batch is activated only after every creation succeeds.
- Activation failure also triggers a cleanup attempt.
- `cleanup_succeeded: false` means the upstream batch may still contain records. Keep the batch ID for investigation.
- `processed_hospitals` counts successful upstream create calls, even if a later cleanup removes those records.

Batch deletion is a compensating action, not an atomic transaction. Network failures can make the final upstream state uncertain.

## Tests

```bash
pytest -q
```

The service tests use a fake upstream client, so they don't create test records in the shared deployed API.

## Deploy to Render

1. Push this repository to GitHub.
2. Create a Render Web Service from the repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Optional environment variable: `HOSPITAL_API_BASE_URL=https://hospital-directory.onrender.com`
6. Verify `/`, `/docs`, and a CSV upload against the deployed service.

## Important upstream contract check

Before submission, verify the live upstream API behavior for `creation_batch_id`, inactive creation, batch activation, and deletion. The published OpenAPI schema gives `active` a default of `true`, while the assignment describes batch-created hospitals as initially inactive. The application relies on the upstream service's batch behavior and does not try to override the `active` field.
