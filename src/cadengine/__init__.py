"""CadEngine Python SDK — CAD file analysis, cost estimation, manufacturing intelligence.

Usage:
    from cadengine import CadEngineClient

    client = CadEngineClient(api_key="ce_live_...")
    result = client.analyze("bracket.step", include_cost=True)
"""

from cadengine.client import ApiError, CadEngineClient

__version__ = "0.1.0"

__all__ = ["CadEngineClient", "ApiError", "__version__"]
