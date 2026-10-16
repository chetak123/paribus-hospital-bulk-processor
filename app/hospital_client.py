from typing import Any, Dict, List
import httpx


class HospitalAPIError(RuntimeError):
    """An upstream Hospital Directory API request failed."""


class HospitalAPIClient:
    """Small adapter around the existing Hospital Directory API."""

    def __init__(self, base_url: str, timeout_seconds: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(
                    method, f"{self.base_url}{path}", **kwargs
                )
                response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            raise HospitalAPIError(f"{method} {path} failed: {exc}") from exc

        if response.status_code == 204 or not response.content:
            return None

        try:
            return response.json()
        except ValueError as exc:
            raise HospitalAPIError(
                f"{method} {path} returned invalid JSON."
            ) from exc

    async def create_hospital(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/hospitals/", json=payload)

    async def activate_batch(self, batch_id: str) -> Any:
        return await self._request(
            "PATCH", f"/hospitals/batch/{batch_id}/activate"
        )

    async def delete_batch(self, batch_id: str) -> Any:
        return await self._request("DELETE", f"/hospitals/batch/{batch_id}")
