"""Tests for CadEngineClient — transport mocked, no network."""

from __future__ import annotations

import json

import httpx
import pytest

from cadengine import ApiError, CadEngineClient
from cadengine.config import config_path, resolve_api_key, resolve_base_url, save_config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point config + env at a sandbox so tests never touch the real machine."""
    monkeypatch.setenv("CADENGINE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("CADENGINE_API_KEY", raising=False)
    monkeypatch.delenv("CADENGINE_API_URL", raising=False)
    return tmp_path


def make_client(handler, api_key: str | None = "ce_live_test") -> CadEngineClient:
    client = CadEngineClient(api_key=api_key, base_url="https://api.test")
    client._client = httpx.Client(
        base_url="https://api.test", transport=httpx.MockTransport(handler)
    )
    return client


# -- config resolution --------------------------------------------------------


def test_api_key_priority(monkeypatch):
    save_config({"api_key": "ce_from_file"})
    assert resolve_api_key() == "ce_from_file"
    monkeypatch.setenv("CADENGINE_API_KEY", "ce_from_env")
    assert resolve_api_key() == "ce_from_env"
    assert resolve_api_key("ce_explicit") == "ce_explicit"


def test_base_url_default_and_override(monkeypatch):
    assert resolve_base_url() == "https://api.cadengine.tech"
    monkeypatch.setenv("CADENGINE_API_URL", "http://localhost:8080/")
    assert resolve_base_url() == "http://localhost:8080"


def test_save_config_merges():
    save_config({"api_key": "a"})
    save_config({"base_url": "http://x"})
    data = json.loads(config_path().read_text())
    assert data == {"api_key": "a", "base_url": "http://x"}


# -- client behaviour ---------------------------------------------------------


def test_health_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/health"
        return httpx.Response(200, json={"status": "ok", "version": "0.2.0"})

    with make_client(handler) as client:
        assert client.health()["status"] == "ok"


def test_analyze_sends_auth_and_fields(tmp_path):
    part = tmp_path / "part.step"
    part.write_text("ISO-10303-21;")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/analyze"
        assert request.headers["Authorization"] == "Bearer ce_live_test"
        body = request.read()
        assert b'name="file"' in body
        assert b"part.step" in body
        assert b'name="include_cost"' in body
        return httpx.Response(200, json={"job_id": "j1", "status": "completed"})

    with make_client(handler) as client:
        result = client.analyze(part, include_cost=True)
    assert result["job_id"] == "j1"


def test_analyze_missing_file():
    with make_client(lambda r: httpx.Response(200)) as client:
        with pytest.raises(FileNotFoundError):
            client.analyze("does-not-exist.step")


def test_error_envelope_parsed(tmp_path):
    part = tmp_path / "part.step"
    part.write_text("data")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "detail": {
                    "error": {
                        "code": "rate_limited",
                        "message": "Rate limit exceeded",
                        "request_id": "req_abc",
                    }
                }
            },
        )

    with make_client(handler) as client:
        with pytest.raises(ApiError) as exc_info:
            client.analyze(part)
    err = exc_info.value
    assert (err.status, err.code, err.request_id) == (429, "rate_limited", "req_abc")


def test_solve_sends_constraints(tmp_path):
    part = tmp_path / "plate.dxf"
    part.write_text("0\nSECTION")

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'name="problem_type"' in body
        assert b"stock_optimization" in body
        assert b'{"quantity": 250}' in body
        return httpx.Response(200, json={"solutions": []})

    with make_client(handler) as client:
        result = client.solve(
            part, problem_type="stock_optimization", constraints={"quantity": 250}
        )
    assert result["solutions"] == []
