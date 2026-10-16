import time
import uuid
from typing import List

from app.csv_parser import parse_hospital_csv
from app.hospital_client import HospitalAPIClient, HospitalAPIError
from app.schemas import BulkResponse, HospitalInput, RowResult


class BulkHospitalService:
    def __init__(self, hospital_client: HospitalAPIClient):
        self.hospital_client = hospital_client

    async def process_csv(self, contents: bytes) -> BulkResponse:
        started = time.perf_counter()
        # Validate everything before creating any upstream records.
        records: List[HospitalInput] = parse_hospital_csv(contents)
        batch_id = str(uuid.uuid4())
        results: List[RowResult] = []
        processed = 0

        for row_number, hospital in enumerate(records, start=1):
            payload = hospital.model_dump()
            payload["creation_batch_id"] = batch_id
            try:
                created = await self.hospital_client.create_hospital(payload)
                hospital_id = created.get("id") if isinstance(created, dict) else None
                results.append(RowResult(
                    row=row_number,
                    name=hospital.name,
                    hospital_id=hospital_id,
                    status="created_inactive",
                ))
                processed += 1
            except HospitalAPIError as exc:
                results.append(RowResult(
                    row=row_number,
                    name=hospital.name,
                    status="failed",
                    error=str(exc),
                ))
                for remaining_number, remaining in enumerate(
                    records[row_number:], start=row_number + 1
                ):
                    results.append(RowResult(
                        row=remaining_number,
                        name=remaining.name,
                        status="not_processed",
                        error="Not attempted because an earlier hospital creation failed.",
                    ))

                cleanup_succeeded = await self._try_delete_batch(batch_id)
                if cleanup_succeeded:
                    for result in results:
                        if result.status == "created_inactive":
                            result.status = "rolled_back"
                return BulkResponse(
                    batch_id=batch_id,
                    total_hospitals=len(records),
                    processed_hospitals=processed,
                    failed_hospitals=1,
                    processing_time_seconds=round(time.perf_counter() - started, 4),
                    batch_activated=False,
                    cleanup_attempted=True,
                    cleanup_succeeded=cleanup_succeeded,
                    status="failed",
                    error="Hospital creation failed; batch was not activated.",
                    hospitals=results,
                )

        try:
            await self.hospital_client.activate_batch(batch_id)
        except HospitalAPIError as exc:
            cleanup_succeeded = await self._try_delete_batch(batch_id)
            if cleanup_succeeded:
                for result in results:
                    result.status = "rolled_back"
            return BulkResponse(
                batch_id=batch_id,
                total_hospitals=len(records),
                processed_hospitals=processed,
                failed_hospitals=0,
                processing_time_seconds=round(time.perf_counter() - started, 4),
                batch_activated=False,
                cleanup_attempted=True,
                cleanup_succeeded=cleanup_succeeded,
                status="failed",
                error=f"All hospitals were created, but batch activation failed: {exc}",
                hospitals=results,
            )

        for result in results:
            result.status = "created_and_activated"

        return BulkResponse(
            batch_id=batch_id,
            total_hospitals=len(records),
            processed_hospitals=processed,
            failed_hospitals=0,
            processing_time_seconds=round(time.perf_counter() - started, 4),
            batch_activated=True,
            cleanup_attempted=False,
            cleanup_succeeded=None,
            status="completed",
            hospitals=results,
        )

    async def _try_delete_batch(self, batch_id: str) -> bool:
        try:
            await self.hospital_client.delete_batch(batch_id)
            return True
        except HospitalAPIError:
            # Preserve cleanup outcome in the response; don't hide the original failure.
            return False
