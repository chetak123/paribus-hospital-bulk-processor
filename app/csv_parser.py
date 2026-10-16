import csv
import io
from typing import List, Optional, Tuple

from pydantic import ValidationError

from app.schemas import HospitalInput

MAX_HOSPITALS = 20
REQUIRED_COLUMNS = {"name", "address"}
ALLOWED_COLUMNS = {"name", "address", "phone"}


class CSVValidationError(ValueError):
    pass


def parse_hospital_csv(contents: bytes) -> List[HospitalInput]:
    text = _decode_contents(contents)
    reader = _create_reader(text)
    _validate_headers(reader.fieldnames)
    records = _parse_records(reader)
    _validate_record_count(records)
    return records


def _decode_contents(contents: bytes) -> str:
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVValidationError("CSV must be UTF-8 encoded.") from exc

    if not text.strip():
        raise CSVValidationError("CSV file is empty.")
    return text


def _create_reader(text: str) -> csv.DictReader:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CSVValidationError("CSV header row is missing.")
    return reader


def _validate_headers(fieldnames: Optional[List[str]]) -> None:
    if not fieldnames:
        raise CSVValidationError("CSV header row is missing.")

    headers = [h.strip().lower() for h in fieldnames if h is not None]
    if len(headers) != len(set(headers)):
        raise CSVValidationError("CSV contains duplicate column names.")

    missing = REQUIRED_COLUMNS - set(headers)
    if missing:
        raise CSVValidationError(
            "Missing required column(s): " + ", ".join(sorted(missing))
        )

    unknown = set(headers) - ALLOWED_COLUMNS
    if unknown:
        raise CSVValidationError(
            "Unsupported column(s): " + ", ".join(sorted(unknown))
        )


def _parse_row(raw_row: dict) -> Tuple[Optional[HospitalInput], Optional[str]]:
    if not raw_row or not any(v and v.strip() for v in raw_row.values() if v is not None):
        return None, None

    row = {
        (k.strip().lower() if k else k): (v.strip() if v is not None else "")
        for k, v in raw_row.items()
        if k is not None
    }

    try:
        record = HospitalInput(
            name=row.get("name", ""),
            address=row.get("address", ""),
            phone=row.get("phone") or None,
        )
        return record, None
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in exc.errors()
        )
        return None, messages


def _parse_records(reader: csv.DictReader) -> List[HospitalInput]:
    records: List[HospitalInput] = []
    errors: List[str] = []

    for row_number, raw_row in enumerate(reader, start=2):
        record, error = _parse_row(raw_row)
        if error:
            errors.append(f"Row {row_number}: {error}")
        elif record:
            records.append(record)

    if errors:
        raise CSVValidationError("Invalid CSV data: " + " | ".join(errors))
    return records


def _validate_record_count(records: List[HospitalInput]) -> None:
    if not records:
        raise CSVValidationError("CSV contains no hospital records.")
    if len(records) > MAX_HOSPITALS:
        raise CSVValidationError(
            f"CSV contains {len(records)} hospitals; maximum allowed is {MAX_HOSPITALS}."
        )
