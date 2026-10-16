# API Contract & Reference

API documentation and contract specification for the **Hospital Bulk Processor** service.

- **Live Deployment:** [https://paribus-hospital-bulk-processor-fkro.onrender.com](https://paribus-hospital-bulk-processor-fkro.onrender.com)
- **Interactive Swagger UI:** [https://paribus-hospital-bulk-processor-fkro.onrender.com/docs](https://paribus-hospital-bulk-processor-fkro.onrender.com/docs)
- **Bulk Endpoint in Swagger UI:** [https://paribus-hospital-bulk-processor-fkro.onrender.com/docs#/default/bulk_create_hospitals_hospitals_bulk_post](https://paribus-hospital-bulk-processor-fkro.onrender.com/docs#/default/bulk_create_hospitals_hospitals_bulk_post)
- **Local Base URL:** `http://localhost:8000`

---

## Overview

The service exposes two HTTP endpoints:
1. `GET /` — Health check endpoint.
2. `POST /hospitals/bulk` — Multipart CSV upload for bulk hospital creation and batch activation with automated compensating rollback.

---

## 1. Health Check

### `GET /`

Checks if the service is alive and healthy.

#### Request
- **Method:** `GET`
- **Path:** `/`
- **Headers:** None required

#### Response — 200 OK
```json
{
  "status": "OK"
}
```

---

## 2. Bulk Upload & Process Hospitals

### `POST /hospitals/bulk`

Uploads a CSV file of hospital records, parses and validates each row, generates a unique batch identifier, sequentially creates hospitals in the upstream [Hospital Directory API](https://hospital-directory.onrender.com), and activates the batch if all rows succeed. If any row fails during creation or activation, an automated rollback deletion is triggered.

#### Request

- **Method:** `POST`
- **Path:** `/hospitals/bulk`
- **Content-Type:** `multipart/form-data`

##### Form Parameters
| Parameter | Type | Required | Description |
|---|---|---|---|
| `file` | `UploadFile` (binary) | Yes | CSV file containing hospital records (`.csv` extension). |

##### CSV Constraints & Rules
- **Encoding:** UTF-8 or UTF-8 with BOM (`utf-8-sig`).
- **File Extension:** Must end in `.csv` (case-insensitive).
- **Max File Size:** 1 MB (1,000,000 bytes).
- **Row Limits:** Between 1 and 20 non-empty hospital records (excluding header row).
- **Required Columns:** `name`, `address` (case-insensitive, whitespace-trimmed).
- **Optional Columns:** `phone`.
- **Unsupported Columns:** Not allowed (CSV will be rejected if unexpected columns are present).
- **Duplicate Headers:** Not allowed.
- **Empty Rows:** Blank or whitespace-only rows are automatically ignored.

##### Sample CSV Content
```csv
name,address,phone
Apollo Hospital, Bannerghatta Road Bengaluru, +918046310000
Fortis Hospital, Cunningham Road Bengaluru, +918041964444
Manipal Hospital, Old Airport Road Bengaluru, +918044444444
```

---

### Responses

#### 200 OK — Batch Completed & Activated
Returned when all hospital records in the CSV are successfully created upstream and the batch is activated.

```json
{
  "batch_id": "97e682d3-1382-411a-a1b4-53a5c6ee1859",
  "total_hospitals": 3,
  "processed_hospitals": 3,
  "failed_hospitals": 0,
  "processing_time_seconds": 1.4821,
  "batch_activated": true,
  "cleanup_attempted": false,
  "cleanup_succeeded": null,
  "status": "completed",
  "error": null,
  "hospitals": [
    {
      "row": 1,
      "name": "Apollo Hospital",
      "hospital_id": 101,
      "status": "created_and_activated",
      "error": null
    },
    {
      "row": 2,
      "name": "Fortis Hospital",
      "hospital_id": 102,
      "status": "created_and_activated",
      "error": null
    },
    {
      "row": 3,
      "name": "Manipal Hospital",
      "hospital_id": 103,
      "status": "created_and_activated",
      "error": null
    }
  ]
}
```

---

#### 400 Bad Request — Invalid File Extension
Returned when the uploaded file does not have a `.csv` extension.

```json
{
  "detail": "Upload a .csv file."
}
```

---

#### 413 Payload Too Large — File Exceeds Size Limit
Returned when the uploaded file is larger than 1 MB.

```json
{
  "detail": "CSV file exceeds 1 MB."
}
```

---

#### 422 Unprocessable Entity — CSV Validation Error
Returned before any upstream calls are initiated if the CSV format or data violates schema constraints.

| Error Condition | Example Error Detail |
|---|---|
| Empty file | `CSV file is empty.` |
| Header missing | `CSV header row is missing.` |
| Missing required column | `Missing required column(s): address` |
| Duplicate column names | `CSV contains duplicate column names.` |
| Unsupported column | `Unsupported column(s): email, rating` |
| No records | `CSV contains no hospital records.` |
| Exceeds 20 records | `CSV contains 25 hospitals; maximum allowed is 20.` |
| Row validation failure | `Invalid CSV data: Row 2: name: String should have at least 1 character` |

##### Example 422 Response:
```json
{
  "detail": "Missing required column(s): address"
}
```

---

#### 502 Bad Gateway — Upstream API Failure & Compensating Rollback
Returned when an upstream call to the Hospital Directory API fails during hospital creation or batch activation. A structured response is returned containing the rollback audit details.

```json
{
  "batch_id": "97e682d3-1382-411a-a1b4-53a5c6ee1859",
  "total_hospitals": 3,
  "processed_hospitals": 1,
  "failed_hospitals": 1,
  "processing_time_seconds": 0.8124,
  "batch_activated": false,
  "cleanup_attempted": true,
  "cleanup_succeeded": true,
  "status": "failed",
  "error": "Hospital creation failed; batch was not activated.",
  "hospitals": [
    {
      "row": 1,
      "name": "Apollo Hospital",
      "hospital_id": 101,
      "status": "rolled_back",
      "error": null
    },
    {
      "row": 2,
      "name": "Fortis Hospital",
      "hospital_id": null,
      "status": "failed",
      "error": "POST /hospitals/ failed: 500 Internal Server Error"
    },
    {
      "row": 3,
      "name": "Manipal Hospital",
      "hospital_id": null,
      "status": "not_processed",
      "error": "Not attempted because an earlier hospital creation failed."
    }
  ]
}
```

> [!NOTE]
> If upstream rollback deletion fails due to network outage, `cleanup_succeeded` will be `false`. In this case, `batch_id` is preserved in the response for manual inspection against the upstream directory.

---

## Schema Definitions

### `BulkResponse`
| Field | Type | Description |
|---|---|---|
| `batch_id` | `string` (UUID) | Unique identifier generated for the processing batch. |
| `total_hospitals` | `integer` | Total number of valid hospital rows parsed from the CSV. |
| `processed_hospitals` | `integer` | Count of hospital records successfully created upstream. |
| `failed_hospitals` | `integer` | Count of hospital records that failed during creation. |
| `processing_time_seconds` | `float` | Wall-clock execution time in seconds. |
| `batch_activated` | `boolean` | `true` if batch was activated; `false` otherwise. |
| `cleanup_attempted` | `boolean` | `true` if compensating rollback deletion was attempted. |
| `cleanup_succeeded` | `boolean` or `null` | `true` if rollback succeeded, `false` if cleanup failed, `null` if no cleanup needed. |
| `status` | `string` | High-level status: `"completed"` or `"failed"`. |
| `error` | `string` or `null` | Top-level error description when failures occur. |
| `hospitals` | `array[RowResult]` | Per-row processing status and error diagnostics. |

### `RowResult`
| Field | Type | Description |
|---|---|---|
| `row` | `integer` | 1-indexed row number from the CSV input. |
| `name` | `string` | Hospital name. |
| `hospital_id` | `integer` or `null` | Primary ID assigned by upstream API (if created). |
| `status` | `string` | State of the record (see Row Status Lifecycle below). |
| `error` | `string` or `null` | Specific failure reason for this row. |

### Row Status Values
| Status | Meaning |
|---|---|
| `created_and_activated` | Record was created upstream and successfully activated in the batch. |
| `created_inactive` | Record was created upstream, awaiting batch activation. |
| `failed` | Record creation call to the upstream API failed. |
| `not_processed` | Row was not attempted because an earlier row failed (fail-fast policy). |
| `rolled_back` | Record was previously created upstream but subsequently deleted via compensating batch rollback. |

---

## Client Usage Examples

### 1. cURL

#### Against Live Render Deployment:
```bash
curl -X POST "https://paribus-hospital-bulk-processor-fkro.onrender.com/hospitals/bulk" \
  -F "file=@csv-files/sample.csv"
```

#### Against Local Instance:
```bash
curl -X POST "http://localhost:8000/hospitals/bulk" \
  -F "file=@csv-files/sample.csv"
```

---

### 2. Python (`httpx`)

```python
import httpx

API_URL = "https://paribus-hospital-bulk-processor-fkro.onrender.com/hospitals/bulk"

with open("csv-files/sample.csv", "rb") as file_handle:
    files = {"file": ("sample.csv", file_handle, "text/csv")}
    response = httpx.post(API_URL, files=files, timeout=30.0)

print(f"Status Code: {response.status_code}")
print(response.json())
```

---

### 3. Node.js (`fetch`)

```javascript
import fs from "node:fs";

const formData = new FormData();
const fileBlob = new Blob([fs.readFileSync("csv-files/sample.csv")], { type: "text/csv" });
formData.append("file", fileBlob, "sample.csv");

const res = await fetch("https://paribus-hospital-bulk-processor-fkro.onrender.com/hospitals/bulk", {
  method: "POST",
  body: formData,
});

const data = await res.json();
console.log(res.status, data);
```

