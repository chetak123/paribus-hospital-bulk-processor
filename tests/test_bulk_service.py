import pytest

from app.bulk_service import BulkHospitalService
from app.hospital_client import HospitalAPIError


CSV = b"name,address,phone\nCity Hospital,MG Road,123\nGeneral Care,HSR,\n"


class FakeHospitalClient:
    def __init__(self, fail_on_create=None, fail_activate=False, fail_delete=False):
        self.calls = []
        self.create_count = 0
        self.fail_on_create = fail_on_create
        self.fail_activate = fail_activate
        self.fail_delete = fail_delete

    async def create_hospital(self, payload):
        self.calls.append(("create", payload))
        self.create_count += 1
        if self.create_count == self.fail_on_create:
            raise HospitalAPIError("simulated create failure")
        return {"id": self.create_count, **payload}

    async def activate_batch(self, batch_id):
        self.calls.append(("activate", batch_id))
        if self.fail_activate:
            raise HospitalAPIError("simulated activation failure")

    async def delete_batch(self, batch_id):
        self.calls.append(("delete", batch_id))
        if self.fail_delete:
            raise HospitalAPIError("simulated cleanup failure")


@pytest.mark.asyncio
async def test_success_creates_all_then_activates_same_batch():
    client = FakeHospitalClient()
    result = await BulkHospitalService(client).process_csv(CSV)

    assert result.status == "completed"
    assert result.total_hospitals == 2
    assert result.processed_hospitals == 2
    assert result.failed_hospitals == 0
    assert result.batch_activated is True
    assert [call[0] for call in client.calls] == ["create", "create", "activate"]
    batch_ids = [call[1]["creation_batch_id"] for call in client.calls[:2]]
    assert batch_ids == [result.batch_id, result.batch_id]


@pytest.mark.asyncio
async def test_creation_failure_attempts_cleanup_and_does_not_activate():
    client = FakeHospitalClient(fail_on_create=2)
    result = await BulkHospitalService(client).process_csv(CSV)

    assert result.status == "failed"
    assert result.batch_activated is False
    assert result.cleanup_attempted is True
    assert result.cleanup_succeeded is True
    assert [call[0] for call in client.calls] == ["create", "create", "delete"]
    assert result.hospitals[0].status == "rolled_back"
    assert result.hospitals[1].status == "failed"


@pytest.mark.asyncio
async def test_reports_cleanup_failure():
    client = FakeHospitalClient(fail_on_create=2, fail_delete=True)
    result = await BulkHospitalService(client).process_csv(CSV)

    assert result.status == "failed"
    assert result.cleanup_attempted is True
    assert result.cleanup_succeeded is False
    assert result.batch_activated is False


@pytest.mark.asyncio
async def test_activation_failure_attempts_cleanup():
    client = FakeHospitalClient(fail_activate=True)
    result = await BulkHospitalService(client).process_csv(CSV)

    assert result.status == "failed"
    assert result.batch_activated is False
    assert result.cleanup_succeeded is True
    assert [call[0] for call in client.calls] == [
        "create", "create", "activate", "delete"
    ]
