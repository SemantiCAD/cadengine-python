"""CadEngine command-line interface.

Commands:
    cadengine init          Store your API key in ~/.cadengine/config.json
    cadengine health-check  Verify connectivity and show server capabilities
    cadengine analyze FILE  Analyze a CAD file (--cost, --plan, --json)
    cadengine solve FILE    Solve a manufacturing problem (--problem, --type)
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any

import httpx

from cadengine import __version__
from cadengine.client import ApiError, CadEngineClient
from cadengine.config import resolve_api_key, save_config


def _print_kv(rows: list[tuple[str, Any]]) -> None:
    width = max(len(key) for key, _ in rows)
    for key, value in rows:
        print(f"{key.ljust(width + 2)}{value}")


def _client(args: argparse.Namespace) -> CadEngineClient:
    return CadEngineClient(base_url=getattr(args, "base_url", None))


def cmd_init(_args: argparse.Namespace) -> int:
    print("Paste your API key (from Dashboard -> API Keys).")
    api_key = getpass.getpass("API key: ").strip()
    if not api_key:
        print("No key entered — aborted.", file=sys.stderr)
        return 1
    if not api_key.startswith("ce_"):
        print("Warning: keys normally start with 'ce_'. Saving anyway.", file=sys.stderr)
    path = save_config({"api_key": api_key})
    print(f"Saved to {path}. Run 'cadengine health-check' to verify.")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    with _client(args) as client:
        info = client.health()
    _print_kv(
        [
            ("status", info.get("status", "?")),
            ("version", info.get("version", "?")),
            ("occ", "available" if info.get("occ_available") else "unavailable (text fallback)"),
            ("llm", "available" if info.get("llm_available") else "unavailable"),
            ("formats", ", ".join(info.get("supported_formats", []))),
            ("max file", f"{info.get('max_file_mb', '?')} MB"),
        ]
    )
    if resolve_api_key() is None:
        print("\nNote: no API key configured — run 'cadengine init'.", file=sys.stderr)
    return 0 if info.get("status") == "ok" else 1


def _summarize_analyze(result: dict[str, Any]) -> None:
    features = result.get("features", {})
    derived = features.get("derived", {})
    rows: list[tuple[str, Any]] = [
        ("job", result.get("job_id", "?")),
        ("status", result.get("status", "?")),
        ("format", features.get("format", "?")),
        ("classification", features.get("classification", "?")),
        ("confidence", features.get("confidence", "?")),
        ("parse time", f"{result.get('parse_duration_ms', '?')} ms"),
    ]
    volume = derived.get("volume_m3") or derived.get("volume_m3_bbox")
    if volume is not None:
        proxy = " (bbox proxy)" if derived.get("is_text_parsed") else ""
        rows.append(("volume", f"{volume} m3{proxy}"))
    cost = result.get("cost")
    if cost:
        rows.append(("total cost", f"{cost.get('total_cost_try', '?')} TRY"))
    _print_kv(rows)
    warnings = result.get("warnings") or []
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)


def cmd_analyze(args: argparse.Namespace) -> int:
    with _client(args) as client:
        result = client.analyze(
            args.file,
            include_cost=args.cost,
            include_plan=args.plan,
            cost_rates=json.loads(args.cost_rates) if args.cost_rates else None,
        )
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        print()
    else:
        _summarize_analyze(result)
    return 0


def cmd_solve(args: argparse.Namespace) -> int:
    constraints = json.loads(args.constraints) if args.constraints else None
    with _client(args) as client:
        result = client.solve(
            args.file,
            problem=args.problem,
            problem_type=args.type,
            constraints=constraints,
        )
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        print()
    else:
        solutions = result.get("solutions") or []
        print(f"solutions: {len(solutions)}")
        for i, solution in enumerate(solutions, 1):
            print(f"\n--- solution {i} ---")
            json.dump(solution, sys.stdout, indent=2)
            print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cadengine",
        description="CadEngine CLI — analyze CAD files and solve manufacturing problems.",
    )
    parser.add_argument("--version", action="version", version=f"cadengine {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Store your API key locally")
    p_init.set_defaults(func=cmd_init)

    p_health = sub.add_parser("health-check", help="Verify connectivity to the API")
    p_health.add_argument("--base-url", dest="base_url", help="Override the API base URL")
    p_health.set_defaults(func=cmd_health)

    p_analyze = sub.add_parser("analyze", help="Analyze a CAD file")
    p_analyze.add_argument("file", help="Path to a .step/.stp/.dxf/.dwg file")
    p_analyze.add_argument("--cost", action="store_true", help="Include cost estimate (+0.5 units)")
    p_analyze.add_argument("--plan", action="store_true", help="Include production plan (+1.5 units)")
    p_analyze.add_argument("--cost-rates", dest="cost_rates", help="JSON object of cost rate overrides")
    p_analyze.add_argument("--json", action="store_true", help="Print the full JSON response")
    p_analyze.add_argument("--base-url", dest="base_url", help="Override the API base URL")
    p_analyze.set_defaults(func=cmd_analyze)

    p_solve = sub.add_parser("solve", help="Solve a manufacturing problem from a CAD file")
    p_solve.add_argument("file", help="Path to the CAD file")
    p_solve.add_argument("--problem", help="Free-text problem statement")
    p_solve.add_argument(
        "--type",
        help="Problem type (dfm_analysis, stock_optimization, cost_estimation, ...)",
    )
    p_solve.add_argument("--constraints", help='JSON constraints, e.g. \'{"quantity": 250}\'')
    p_solve.add_argument("--json", action="store_true", help="Print the full JSON response")
    p_solve.add_argument("--base-url", dest="base_url", help="Override the API base URL")
    p_solve.set_defaults(func=cmd_solve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ApiError as e:
        detail = f" (request {e.request_id})" if e.request_id else ""
        print(f"error [{e.status}] {e.code}: {e.message}{detail}", file=sys.stderr)
        return 1
    except httpx.ConnectError:
        print(
            "error: could not connect to the API — check the base URL and your network.",
            file=sys.stderr,
        )
        return 1
    except httpx.TimeoutException:
        print("error: request timed out — retry, or increase the timeout.", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON argument: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
