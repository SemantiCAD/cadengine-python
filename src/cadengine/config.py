"""Configuration resolution for the CadEngine SDK and CLI.

Priority (highest first):
1. Explicit arguments (``api_key=`` / ``base_url=``)
2. Environment variables (``CADENGINE_API_KEY`` / ``CADENGINE_API_URL``)
3. Config file (``~/.cadengine/config.json``)
4. Built-in defaults (base URL only)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_BASE_URL = "https://api.cadengine.tech"

ENV_API_KEY = "CADENGINE_API_KEY"
ENV_API_URL = "CADENGINE_API_URL"


def config_path() -> Path:
    """Location of the CLI config file (override dir with CADENGINE_CONFIG_DIR)."""
    base = os.environ.get("CADENGINE_CONFIG_DIR")
    root = Path(base) if base else Path.home() / ".cadengine"
    return root / "config.json"


def load_config() -> dict:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(values: dict) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**load_config(), **values}
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return path


def resolve_api_key(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    env = os.environ.get(ENV_API_KEY)
    if env:
        return env
    return load_config().get("api_key") or None


def resolve_base_url(explicit: str | None = None) -> str:
    if explicit:
        return explicit.rstrip("/")
    env = os.environ.get(ENV_API_URL)
    if env:
        return env.rstrip("/")
    from_config = load_config().get("base_url")
    if from_config:
        return str(from_config).rstrip("/")
    return DEFAULT_BASE_URL
