import csv
import io
from typing import List

from pydantic import ValidationError

from app.schemas import HospitalInput


MAX_HOSPITALS = 20
REQUIRED_COLUMNS = {"name", "address"}
ALLOWED_COLUMNS = {"name", "address", "phone"}


class CSVValidationError(ValueError):
    """Raised when the uploaded CSV cannot safely be processed."""


def parse_hospital_csv(contents: bytes) -> List[HospitalInput]:
    """Parse and validate the complete CSV before any upstream side effects."""
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVValidationError("CSV must be UTF-8 encoded.") from exc

    if not text.strip():
        raise CSVValidationError("CSV file is empty.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CSVValidationError("CSV header row is missing.")

    headers = [header.strip().lower() for header in reader.fieldnames if header is not None]
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

    # DictReader keys are the original header strings; normalize them explicitly.
    records = []
    errors = []
    for row_number, raw_row in enumerate(reader, start=2):
        if raw_row is None or not any(
            value is not None and value.strip() for value in raw_row.values()
        ):
            continue

        row = {
            (key.strip().lower() if key else key): (value.strip() if value is not None else "")
            for key, value in raw_row.items()
            if key is not None
        }

        try:
            record = HospitalInput(
                name=row.get("name", ""),
                address=row.get("address", ""),
                phone=row.get("phone") or None,
            )
        except ValidationError as exc:
            messages = "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in exc.errors()
            )
            errors.append(f"Row {row_number}: {messages}")
            continue

        records.append(record)

    if errors:
        raise CSVValidationError("Invalid CSV data: " + " | ".join(errors))
    if not records:
        raise CSVValidationError("CSV contains no hospital records.")
    if len(records) > MAX_HOSPITALS:
        raise CSVValidationError(
            f"CSV contains {len(records)} hospitals; maximum allowed is {MAX_HOSPITALS}."
        )

    return records
