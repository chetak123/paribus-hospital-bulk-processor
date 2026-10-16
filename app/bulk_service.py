import time
import uuid
from typing import List, Optional, Tuple

from app.csv_parser import parse_hospital_csv
from app.hospital_client import HospitalAPIClient, HospitalAPIError
from app.schemas import BulkResponse, HospitalInput, RowResult


class BulkHospitalService:
    def __init__(self, hospital_client: HospitalAPIClient):
        self.hospital_client = hospital_client

    async def process_csv(self, contents: bytes) -> BulkResponse:
        started = time.perf_counter()
        records = parse_hospital_csv(contents)
        batch_id = str(uuid.uuid4())

        results, processed, creation_failed = await self._create_hospitals(batch_id, records)
        if creation_failed:
            cleanup_succeeded = await self._rollback(batch_id, results)
            return self._build_response(
                batch_id=batch_id,
                total=len(records),
                processed=processed,
                failed=1,
                started=started,
                batch_activated=False,
                cleanup_attempted=True,
                cleanup_succeeded=cleanup_succeeded,
                status="failed",
                error="Hospital creation failed; batch was not activated.",
                hospitals=results,
            )

        activation_error = await self._activate_batch(batch_id)
        if activation_error:
            cleanup_succeeded = await self._rollback(batch_id, results)
            return self._build_response(
                batch_id=batch_id,
                total=len(records),
                processed=processed,
                failed=0,
                started=started,
                batch_activated=False,
                cleanup_attempted=True,
                cleanup_succeeded=cleanup_succeeded,
                status="failed",
                error=f"All hospitals were created, but batch activation failed: {activation_error}",
                hospitals=results,
            )

        for result in results:
            result.status = "created_and_activated"

        return self._build_response(
            batch_id=batch_id,
            total=len(records),
            processed=processed,
            failed=0,
            started=started,
            batch_activated=True,
            cleanup_attempted=False,
            cleanup_succeeded=None,
            status="completed",
            error=None,
            hospitals=results,
        )

    async def _create_hospitals(
        self, batch_id: str, records: List[HospitalInput]
    ) -> Tuple[List[RowResult], int, bool]:
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
                self._mark_unprocessed(records[row_number:], row_number + 1, results)
                return results, processed, True

        return results, processed, False

    def _mark_unprocessed(
        self, remaining: List[HospitalInput], start_row: int, results: List[RowResult]
    ) -> None:
        for idx, item in enumerate(remaining, start=start_row):
            results.append(RowResult(
                row=idx,
                name=item.name,
                status="not_processed",
                error="Not attempted because an earlier hospital creation failed.",
            ))

    async def _activate_batch(self, batch_id: str) -> Optional[str]:
        try:
            await self.hospital_client.activate_batch(batch_id)
            return None
        except HospitalAPIError as exc:
            return str(exc)

    async def _rollback(self, batch_id: str, results: List[RowResult]) -> bool:
        cleanup_succeeded = await self._try_delete_batch(batch_id)
        if cleanup_succeeded:
            for result in results:
                if result.status == "created_inactive":
                    result.status = "rolled_back"
        return cleanup_succeeded

    async def _try_delete_batch(self, batch_id: str) -> bool:
        try:
            await self.hospital_client.delete_batch(batch_id)
            return True
        except HospitalAPIError:
            return False

    def _build_response(
        self,
        batch_id: str,
        total: int,
        processed: int,
        failed: int,
        started: float,
        batch_activated: bool,
        cleanup_attempted: bool,
        cleanup_succeeded: Optional[bool],
        status: str,
        error: Optional[str],
        hospitals: List[RowResult],
    ) -> BulkResponse:
        return BulkResponse(
            batch_id=batch_id,
            total_hospitals=total,
            processed_hospitals=processed,
            failed_hospitals=failed,
            processing_time_seconds=round(time.perf_counter() - started, 4),
            batch_activated=batch_activated,
            cleanup_attempted=cleanup_attempted,
            cleanup_succeeded=cleanup_succeeded,
            status=status,
            error=error,
            hospitals=hospitals,
        )
