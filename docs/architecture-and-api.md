# Hospital Bulk Processor: Architecture & API Contract

Comprehensive guide detailing the system architecture, component design, failure recovery semantics, and complete API contract for the **Hospital Bulk Processor**.

- **Live Deployment:** [https://paribus-hospital-bulk-processor-fkro.onrender.com](https://paribus-hospital-bulk-processor-fkro.onrender.com)
- **Interactive OpenAPI Docs:** [https://paribus-hospital-bulk-processor-fkro.onrender.com/docs](https://paribus-hospital-bulk-processor-fkro.onrender.com/docs)
- **Direct Bulk Endpoint Swagger:** [https://paribus-hospital-bulk-processor-fkro.onrender.com/docs#/default/bulk_create_hospitals_hospitals_bulk_post](https://paribus-hospital-bulk-processor-fkro.onrender.com/docs#/default/bulk_create_hospitals_hospitals_bulk_post)
- **Upstream Hospital Directory Service:** [https://hospital-directory.onrender.com](https://hospital-directory.onrender.com)

---

## Part 1: System Architecture

### 1. Architectural Philosophy
The **Hospital Bulk Processor** is an asynchronous FastAPI middleware service that accepts CSV files of up to 20 hospital records and bulk-provisions them into an existing upstream Hospital Directory API.
- **Zero Local Persistence:** The upstream service is the single source of truth; no local database or cache is maintained.
- **Strict Pre-Validation Boundary:** The incoming CSV is completely verified in memory (file size ≤ 1 MB, extension, header structure, row counts, Pydantic type validation) before invoking any external endpoints.
- **Compensating Transaction Semantics (Saga Pattern):** To prevent orphaned "inactive" records in the upstream service when an error occurs during creation or activation, the processor executes an automated compensating batch deletion (`DELETE /hospitals/batch/{batch_id}`).

---

### 2. Architectural Blueprint

```
Client (HTTP Multipart Upload)
              │
              ▼
   POST /hospitals/bulk
   ┌────────────────────────────────────────────────────────┐
   │ app/main.py (FastAPI App & HTTP Error Translation)     │
   │  - Size limit: 1 MB                                    │
   │  - Extension check: .csv                               │
   └──────────────────────────┬─────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │ app/csv_parser.py (CSV Parsing & Validation)           │
   │  - Validates UTF-8 / BOM encoding                      │
   │  - Checks required headers: name, address              │
   │  - Enforces max 20 rows & per-row Pydantic models      │
   └──────────────────────────┬─────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │ app/bulk_service.py (Batch Orchestration Engine)       │
   │  - Generates unique UUID batch_id                      │
   │  - Sequential creation loop with fail-fast             │
   │  - Atomic batch activation on success                  │
   │  - Automatic compensating rollback on error            │
   └──────────────────────────┬─────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │ app/hospital_client.py (HTTP Adapter)                  │
   │  - POST /hospitals/ (tag with creation_batch_id)       │
   │  - PATCH /hospitals/batch/{batch_id}/activate          │
   │  - DELETE /hospitals/batch/{batch_id} (compensating)   │
   └──────────────────────────┬─────────────────────────────┘
                              │
                              ▼ (HTTPS)
   Upstream Hospital Directory API (hospital-directory.onrender.com)
```

---

### 3. Execution Workflows & Failure Semantics

```
Success Path:
CSV Upload ──> Strict Validation ──> Sequential Creation ──> Batch Activation ──> 200 OK

Failure Path (Creation or Activation Error):
CSV Upload ──> Upstream Error ──> Abort Remaining ──> Compensating DELETE ──> 502 Bad Gateway
```

#### Why Sequential Creation with Compensating Rollback?
1. **Predictability:** Sequential execution allows immediate termination upon the very first error, halting downstream requests and saving upstream resources.
2. **Deterministic Rollback:** If row $N$ fails, we know exactly rows $1 \dots N-1$ were created in the upstream batch. The compensating deletion cleans up the entire batch cleanly.
3. **Auditability:** Every row result explicitly tracks whether it was `created_and_activated`, `failed`, `not_processed`, or `rolled_back`.

---

### 4. Codebase Structure

```
paribus-hospital-bulk-processor/
├── app/
│   ├── main.py              # Application factory, endpoints, and HTTP status handling
│   ├── schemas.py           # Pydantic schemas (HospitalInput, RowResult, BulkResponse)
│   ├── csv_parser.py        # Complete CSV verification and row-level parsing
│   ├── bulk_service.py      # Business logic: batch workflow, activation, and rollback
│   └── hospital_client.py   # HTTP adapter for the upstream Hospital Directory API
├── csv-files/
│   ├── sample.csv           # 15 sample hospital records for testing
│   └── hospital.csv         # 2 sample hospital records for minimal testing
├── docs/
│   ├── api.md               # Dedicated API reference and request/response specifications
│   ├── architecture.md      # Detailed architectural diagrams and design rationale
│   └── architecture-and-api.md # This consolidated technical guide
├── tests/
│   ├── test_csv_parser.py   # Unit tests for CSV validation logic
│   └── test_bulk_service.py # Unit tests for service workflow and rollback compensation
├── Dockerfile               # Production container image definition
├── requirements.txt         # Dependencies (FastAPI, Uvicorn, HTTPX, Pydantic, Pytest)
└── README.md                # Main repository README
```

---

## Part 2: API Contract Specification

### Base URLs
- **Live Render Deployment:** `https://paribus-hospital-bulk-processor-fkro.onrender.com`
- **Local Development:** `http://localhost:8000`

---

### Endpoint 1: Health Check
`GET /`

#### Response — 200 OK
```json
{
  "status": "OK"
}
```

---

### Endpoint 2: Bulk Create Hospitals
`POST /hospitals/bulk`

Accepts a multipart CSV file upload and orchestrates the bulk hospital creation.

#### Request Parameters
- **Content-Type:** `multipart/form-data`
- **Body Field:** `file` (Binary `.csv` file, max size 1 MB)

#### CSV Requirements
- **Required Columns:** `name` (string, min 1 char), `address` (string, min 1 char).
- **Optional Columns:** `phone` (string).
- **Unsupported Columns:** Not allowed (raises HTTP 422).
- **Row Limits:** Minimum 1 record, maximum 20 records.

#### Success Response — HTTP 200 OK
```json
{
  "batch_id": "b18b53e7-3f33-4f9e-a89a-07f9c2d1d05a",
  "total_hospitals": 2,
  "processed_hospitals": 2,
  "failed_hospitals": 0,
  "processing_time_seconds": 0.942,
  "batch_activated": true,
  "cleanup_attempted": false,
  "cleanup_succeeded": null,
  "status": "completed",
  "error": null,
  "hospitals": [
    {
      "row": 1,
      "name": "City Hospital",
      "hospital_id": 204,
      "status": "created_and_activated",
      "error": null
    },
    {
      "row": 2,
      "name": "General Care",
      "hospital_id": 205,
      "status": "created_and_activated",
      "error": null
    }
  ]
}
```

#### Upstream Error Response — HTTP 502 Bad Gateway
Returned when an upstream call fails and compensating deletion is triggered.

```json
{
  "batch_id": "b18b53e7-3f33-4f9e-a89a-07f9c2d1d05a",
  "total_hospitals": 2,
  "processed_hospitals": 1,
  "failed_hospitals": 1,
  "processing_time_seconds": 0.518,
  "batch_activated": false,
  "cleanup_attempted": true,
  "cleanup_succeeded": true,
  "status": "failed",
  "error": "Hospital creation failed; batch was not activated.",
  "hospitals": [
    {
      "row": 1,
      "name": "City Hospital",
      "hospital_id": 204,
      "status": "rolled_back",
      "error": null
    },
    {
      "row": 2,
      "name": "General Care",
      "hospital_id": null,
      "status": "failed",
      "error": "POST /hospitals/ failed: 500 Internal Server Error"
    }
  ]
}
```

#### Validation Error Responses
- **HTTP 400 Bad Request:** File does not have `.csv` extension (`detail: "Upload a .csv file."`).
- **HTTP 413 Payload Too Large:** File exceeds 1 MB (`detail: "CSV file exceeds 1 MB."`).
- **HTTP 422 Unprocessable Entity:** Malformed CSV, missing columns, invalid data, or > 20 records (`detail: "<error explanation>"`).

---

### Data Models & Enums

#### `BulkResponse`
- `batch_id` (`string`, UUID): Unique identifier for this bulk run.
- `total_hospitals` (`int`): Count of parsed rows.
- `processed_hospitals` (`int`): Count of rows successfully created upstream.
- `failed_hospitals` (`int`): Count of rows that failed during creation.
- `processing_time_seconds` (`float`): Total wall-clock time in seconds.
- `batch_activated` (`bool`): `true` if batch was activated upstream.
- `cleanup_attempted` (`bool`): `true` if compensating rollback was triggered.
- `cleanup_succeeded` (`bool | null`): Outcome of the rollback deletion call.
- `status` (`string`): Overall status (`completed` or `failed`).
- `error` (`string | null`): Overall error message.
- `hospitals` (`List[RowResult]`): Detailed breakdown of each row.

#### `RowResult`
- `row` (`int`): 1-indexed row number.
- `name` (`string`): Hospital name.
- `hospital_id` (`int | null`): Upstream ID if created.
- `status` (`string`): One of `created_and_activated`, `created_inactive`, `failed`, `not_processed`, `rolled_back`.
- `error` (`string | null`): Diagnostic message if the row encountered a failure.

---

### Quick Verification Commands

#### Against Live Render Service
```bash
# Health check
curl -s https://paribus-hospital-bulk-processor-fkro.onrender.com/

# Upload sample CSV
curl -X POST https://paribus-hospital-bulk-processor-fkro.onrender.com/hospitals/bulk \
  -F "file=@csv-files/hospital.csv"
```

#### Against Local Service
```bash
curl -X POST http://localhost:8000/hospitals/bulk \
  -F "file=@csv-files/hospital.csv"
```

