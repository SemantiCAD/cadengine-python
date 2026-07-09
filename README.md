# cadengine

Python SDK and CLI for the [CadEngine](https://cadengine.tech) API — CAD file
analysis, cost estimation, and manufacturing intelligence.

```bash
pip install cadengine
```

## Quickstart

```python
from cadengine import CadEngineClient

client = CadEngineClient(api_key="ce_live_YOUR_KEY")

result = client.analyze("bracket.step", include_cost=True)
print(result["features"]["classification"])
print(result["cost"]["total_cost_try"])
```

Or from the terminal:

```bash
cadengine init                      # store your API key
cadengine health-check              # verify connectivity
cadengine analyze bracket.step --cost --plan
cadengine solve plate.dxf --type stock_optimization --constraints '{"quantity": 250}'
```

## Configuration

Resolution order (highest priority first):

| Setting  | 1                  | 2                    | 3                          |
| -------- | ------------------ | -------------------- | -------------------------- |
| API key  | `api_key=` arg     | `CADENGINE_API_KEY`  | `~/.cadengine/config.json` |
| Base URL | `base_url=` arg    | `CADENGINE_API_URL`  | `https://api.cadengine.tech` |

## Error handling

API failures raise `cadengine.ApiError` with `.status`, `.code`, `.message`,
and `.request_id` matching the API's error envelope:

```python
from cadengine import ApiError, CadEngineClient

client = CadEngineClient()
try:
    client.analyze("part.step")
except ApiError as e:
    if e.code == "rate_limited":
        ...  # back off and retry
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

Full API documentation: https://cadengine.tech/docs
