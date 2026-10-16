import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.bulk_service import BulkHospitalService
from app.csv_parser import CSVValidationError
from app.hospital_client import HospitalAPIClient
from app.schemas import BulkResponse

UPSTREAM_BASE_URL = os.getenv(
    "HOSPITAL_API_BASE_URL", "https://hospital-directory.onrender.com"
)
MAX_UPLOAD_BYTES = 1_000_000

app = FastAPI(
    title="Hospital Bulk Processing API",
    description="Accepts a CSV and creates hospitals through the Hospital Directory API.",
    version="1.0.0",
)


def build_service() -> BulkHospitalService:
    return BulkHospitalService(HospitalAPIClient(UPSTREAM_BASE_URL))


@app.get("/")
async def health_check():
    return {"status": "OK"}


async def _read_and_validate_file(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file.")

    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV file exceeds 1 MB.")

    return contents


@app.post("/hospitals/bulk", response_model=BulkResponse)
async def bulk_create_hospitals(file: UploadFile = File(...)):
    contents = await _read_and_validate_file(file)
    service = build_service()

    try:
        result = await service.process_csv(contents)
    except CSVValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    status_code = 200 if result.status == "completed" else 502
    return JSONResponse(status_code=status_code, content=result.model_dump())
