# Hospital Bulk Processor

A lightweight FastAPI service that accepts a CSV file and bulk-creates hospitals in the [Hospital Directory API](https://hospital-directory.onrender.com), using batch processing with automatic activation and automated compensating rollback.

---

## Live Deployment

The service is deployed and live on Render:

- **Base URL:** [https://paribus-hospital-bulk-processor-fkro.onrender.com](https://paribus-hospital-bulk-processor-fkro.onrender.com)
- **Interactive Swagger UI:** [https://paribus-hospital-bulk-processor-fkro.onrender.com/docs](https://paribus-hospital-bulk-processor-fkro.onrender.com/docs)
- **Bulk Endpoint in Swagger UI:** [https://paribus-hospital-bulk-processor-fkro.onrender.com/docs#/default/bulk_create_hospitals_hospitals_bulk_post](https://paribus-hospital-bulk-processor-fkro.onrender.com/docs#/default/bulk_create_hospitals_hospitals_bulk_post)

---

## How It Works

1. Upload a CSV file of hospitals via `POST /hospitals/bulk`
2. CSV file is validated strictly in memory (encoding, headers, types, ≤ 20 rows) before making any upstream requests
3. A unique `batch_id` (UUID) is generated for the batch
4. Hospitals are created sequentially against the Hospital Directory API, each tagged with the `creation_batch_id`
5. If **all** rows succeed, the batch is activated in one call (`PATCH /hospitals/batch/{batch_id}/activate`) → hospitals go live
6. If **any** row creation fails or batch activation fails, subsequent rows are skipped and an automated compensating cleanup (`DELETE /hospitals/batch/{batch_id}`) is triggered to prevent leaving orphaned inactive records
7. A complete structured processing report is returned

```
CSV Upload → Strict Validation → Create (sequential) → Activate Batch → 200 OK
                                ↳ (On Upstream Error) → Batch Cleanup (Rollback) → 502 Bad Gateway
```

---

## Project Structure

```
paribus-hospital-bulk-processor/
├── app/
│   ├── main.py              # FastAPI app instance, route handlers, size limits
│   ├── schemas.py           # Pydantic models: HospitalInput, RowResult, BulkResponse
│   ├── csv_parser.py        # Strict CSV validation and row parsing
│   ├── bulk_service.py      # Bulk processing — batch orchestration & rollback logic
│   └── hospital_client.py   # Upstream Hospital Directory API HTTP client
├── csv-files/
│   ├── sample.csv           # 15 sample hospital records
│   └── hospital.csv         # 2 sample hospital records
├── docs/
│   ├── api.md               # Full API contract, schemas, status codes, examples
│   ├── architecture.md      # Architecture, sequence diagrams, failure semantics
│   └── architecture-and-api.md # Consolidated Architecture & API Contract
├── tests/
│   ├── test_csv_parser.py   # CSV parsing and validation unit tests
│   └── test_bulk_service.py # Bulk service, activation, and rollback unit tests
├── Dockerfile               # Container definition for production deployment
├── requirements.txt         # Project dependencies
└── README.md                # Project documentation
```

---

## Setup & Running

### Using pip

```bash
# Clone and enter the project
git clone https://github.com/chetak123/paribus-hospital-bulk-processor.git
cd paribus-hospital-bulk-processor

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --reload
```

### Using uv

```bash
# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate

uv pip install -r requirements.txt

# Run the server
uv run uvicorn app.main:app --reload
```

### Using Docker

```bash
# Build the container image
docker build -t hospital-bulk-processor .

# Run the container
docker run -p 8000:8000 -e PORT=8000 hospital-bulk-processor
```

Server will be available locally at: `http://localhost:8000`  
Interactive docs (Swagger UI): `http://localhost:8000/docs`

---

## Usage

Upload a CSV file containing `name`, `address`, and optional `phone` columns:

### Live Render API:
```bash
curl -X POST https://paribus-hospital-bulk-processor-fkro.onrender.com/hospitals/bulk \
  -F "file=@csv-files/sample.csv"
```

### Local Server:
```bash
curl -X POST http://localhost:8000/hospitals/bulk \
  -F "file=@csv-files/sample.csv"
```

Sample CSV files are provided in `csv-files/`:
- `csv-files/sample.csv` (15 hospitals across Bengaluru and Hyderabad)
- `csv-files/hospital.csv` (2 minimal hospital records)

See [docs/api.md](docs/api.md) for the complete request/response contract and examples.

---

## Failure Semantics & Compensating Actions

| HTTP Status | Trigger Condition | Response |
|---|---|---|
| **200 OK** | All rows created and batch activated upstream | Structured `BulkResponse` (`status="completed"`) |
| **400 Bad Request** | Non-CSV file uploaded | `{"detail": "Upload a .csv file."}` |
| **413 Payload Too Large** | Uploaded file exceeds 1 MB | `{"detail": "CSV file exceeds 1 MB."}` |
| **422 Unprocessable Entity** | CSV validation failure (missing/extra columns, empty file, invalid row data, > 20 records) | `{"detail": "<error message>"}` |
| **502 Bad Gateway** | Upstream API failure during creation or activation | Structured `BulkResponse` (`status="failed"`, `cleanup_attempted=True`, `cleanup_succeeded=True/False`) |

- **Zero Upstream Side Effects on Validation Failure:** If the CSV is invalid, HTTP 422 is returned immediately; no requests are sent to the upstream API.
- **Fail-Fast Creation:** On the first creation error, processing halts and later rows are marked `not_processed`.
- **Automated Compensating Rollback:** An automated `DELETE /hospitals/batch/{batch_id}` request is issued to delete previously created records in the batch, marking them as `rolled_back`.
- **Audit Preservation:** If the rollback request itself fails, `cleanup_succeeded: false` is returned with the `batch_id` preserved for manual investigation.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HOSPITAL_API_BASE_URL` | `https://hospital-directory.onrender.com` | Upstream Hospital Directory API base URL |
| `PORT` | `8000` | Port for the Uvicorn web server |

---

## Running Tests

```bash
# Run unit test suite
pytest

# Verbose output
pytest -v
```

Tests use a mocked upstream client (`FakeHospitalClient`) so they run safely without modifying data in the live upstream API.

---

## Documentation

- [API Contract & Reference](docs/api.md) — endpoints, CSV specifications, response models, status codes, and code examples
- [Architecture & Design](docs/architecture.md) — module responsibilities, sequence diagrams, and failure/rollback semantics
- [Consolidated Architecture & API Guide](docs/architecture-and-api.md) — complete single-document technical specification
