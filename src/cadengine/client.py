"""HTTP client for the CadEngine API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from cadengine.config import resolve_api_key, resolve_base_url


class ApiError(Exception):
    """Raised when the API returns an error envelope.

    Attributes:
        status: HTTP status code.
        code: Machine-readable error code (e.g. ``rate_limited``).
        message: Human-readable message.
        request_id: Server-side request id, when available.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        request_id: str | None = None,
    ) -> None:
        super().__init__(f"[{status}] {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id


def _raise_for_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    code = "http_error"
    message = response.reason_phrase or "Request failed"
    request_id: str | None = None
    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError):
        data = None
    if isinstance(data, dict):
        # The API nests the envelope under FastAPI's "detail" for HTTPException
        # responses: {"detail": {"error": {...}}}. Direct envelopes also occur.
        envelope = data.get("detail", data)
        if isinstance(envelope, str):
            message = envelope
        elif isinstance(envelope, dict):
            error = envelope.get("error", envelope)
            if isinstance(error, dict):
                code = error.get("code", code)
                message = error.get("message", message)
                request_id = error.get("request_id")
    raise ApiError(response.status_code, code, message, request_id)


class CadEngineClient:
    """Synchronous client for the CadEngine API.

    Args:
        api_key: API key (``ce_live_...``). Falls back to the
            ``CADENGINE_API_KEY`` environment variable, then
            ``~/.cadengine/config.json``.
        base_url: API root. Falls back to ``CADENGINE_API_URL``, then
            ``https://api.cadengine.tech``.
        timeout: Request timeout in seconds (default 120 — parses can be slow
            for large assemblies).
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = resolve_api_key(api_key)
        self.base_url = resolve_base_url(base_url)
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    # -- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CadEngineClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- internals -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    @staticmethod
    def _file_tuple(path: str | Path) -> tuple[str, bytes]:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"No such file: {p}")
        return (p.name, p.read_bytes())

    # -- endpoints -----------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """GET /v1/health — server status and capabilities (no auth needed)."""
        response = self._client.get("/v1/health")
        _raise_for_error(response)
        return response.json()

    def analyze(
        self,
        file: str | Path,
        *,
        include_cost: bool = False,
        include_plan: bool = False,
        cost_rates: dict[str, float] | None = None,
        llm_provider: str | None = None,
    ) -> dict[str, Any]:
        """POST /v1/analyze — parse a CAD file into features (+ cost, + plan).

        Args:
            file: Path to a ``.step``/``.stp``/``.dxf``/``.dwg`` file.
            include_cost: Add a cost estimate (+0.5 units).
            include_plan: Add a CNC production plan (+1.5 units).
            cost_rates: Optional numeric overrides for the cost model.
            llm_provider: Optional LLM provider override for plan generation.
        """
        data: dict[str, str] = {}
        if include_cost:
            data["include_cost"] = "true"
        if include_plan:
            data["include_plan"] = "true"
        if cost_rates:
            data["cost_rates"] = json.dumps(cost_rates)
        if llm_provider:
            data["llm_provider"] = llm_provider

        response = self._client.post(
            "/v1/analyze",
            headers=self._headers(),
            data=data,
            files={"file": self._file_tuple(file)},
        )
        _raise_for_error(response)
        return response.json()

    def solve(
        self,
        file: str | Path,
        *,
        problem: str | None = None,
        problem_type: str | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /v1/solve — answer a manufacturing problem from a CAD file.

        Args:
            file: Path to the CAD file.
            problem: Free-text problem statement (type is inferred if
                ``problem_type`` is omitted).
            problem_type: Explicit type, e.g. ``dfm_analysis`` or
                ``stock_optimization``.
            constraints: Structured constraints, e.g. ``{"quantity": 250}``.
        """
        data: dict[str, str] = {}
        if problem:
            data["problem"] = problem
        if problem_type:
            data["problem_type"] = problem_type
        if constraints:
            data["constraints"] = json.dumps(constraints)

        response = self._client.post(
            "/v1/solve",
            headers=self._headers(),
            data=data,
            files={"file": self._file_tuple(file)},
        )
        _raise_for_error(response)
        return response.json()
