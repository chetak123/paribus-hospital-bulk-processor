from pydantic import BaseModel, Field
from typing import Optional, List


class HospitalInput(BaseModel):
    name: str = Field(min_length=1)
    address: str = Field(min_length=1)
    phone: Optional[str] = None


class HospitalCreatePayload(HospitalInput):
    creation_batch_id: str


class RowResult(BaseModel):
    row: int
    name: str
    hospital_id: Optional[int] = None
    status: str
    error: Optional[str] = None


class BulkResponse(BaseModel):
    batch_id: str
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    processing_time_seconds: float
    batch_activated: bool
    cleanup_attempted: bool = False
    cleanup_succeeded: Optional[bool] = None
    status: str
    error: Optional[str] = None
    hospitals: List[RowResult]
