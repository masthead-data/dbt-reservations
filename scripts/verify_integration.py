#!/usr/bin/env python3
"""
Verify dbt integration test output.

Checks two things:
  1. manifest.json — sql_header config was resolved correctly by the macro (after `dbt compile`)
  2. target/run/ SQL files — sql_header statement is physically present in run DDL (after `dbt run`)

Run from inside integration_tests/:
    python ../scripts/verify_integration.py --target-path <path>
"""
import argparse
import json
import sys
from pathlib import Path

RESERVATION_EDITIONS = (
    "projects/masthead-prod/locations/us/reservations/default-pipeline"
)

# node_id → expected substring in sql_header (None = must be empty)
MANIFEST_CHECKS: dict[str, str | None] = {
    "model.bq_reservations_sample.slots": f'SET @@reservation= "{RESERVATION_EDITIONS}";',
    "model.bq_reservations_sample.on_demand": 'SET @@reservation= "none";',
    "model.bq_reservations_sample.default": None,  # null reservation → no header
}

# model name → expected substring in run SQL (None = must NOT contain SET @@reservation=)
RUN_CHECKS: dict[str, str | None] = {
    "slots": f'SET @@reservation= "{RESERVATION_EDITIONS}";',
    "on_demand": 'SET @@reservation= "none";',
    "default": None,
}


def find_run_sql(run_dir: Path, model_name: str) -> Path | None:
    """Search recursively — dbt-core nests under <project>/models/..., fusion uses flat paths."""
    matches = list(run_dir.rglob(f"{model_name}.sql"))
    if not matches:
        return None
    # Prefer the deepest path (dbt-core nested > fusion flat) so that when both
    # exist (stale target dir) the nested one wins — but in practice each session
    # uses its own --target-path so there should be exactly one match.
    return sorted(matches, key=lambda p: len(p.parts))[-1]


def check_manifest(target: Path) -> list[str]:
    errors = []
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        return [f"manifest.json not found at {manifest_path}"]

    nodes = json.loads(manifest_path.read_text()).get("nodes", {})
    for node_id, expected in MANIFEST_CHECKS.items():
        node = nodes.get(node_id)
        if not node:
            errors.append(f"[manifest] Node not found: {node_id}")
            continue
        actual: str = node.get("config", {}).get("sql_header") or ""
        if expected is None:
            if actual.strip():
                errors.append(
                    f"[manifest] {node_id}: expected empty sql_header, got: {actual!r}"
                )
        else:
            if expected not in actual:
                errors.append(
                    f"[manifest] {node_id}: expected {expected!r} in sql_header\n"
                    f"           got: {actual!r}"
                )
    return errors


def check_run_sql(target: Path) -> list[str]:
    errors = []
    run_dir = target / "run"
    if not run_dir.exists():
        return [f"target/run/ not found at {run_dir} — did you run `dbt run`?"]

    for model_name, expected in RUN_CHECKS.items():
        sql_file = find_run_sql(run_dir, model_name)
        if sql_file is None:
            errors.append(f"[run] SQL file not found for model '{model_name}' under {run_dir}")
            continue
        content = sql_file.read_text()
        if expected is None:
            if "SET @@reservation=" in content:
                errors.append(
                    f"[run] {model_name}: should NOT contain SET @@reservation= but does\n"
                    f"      file: {sql_file}"
                )
        else:
            if expected not in content:
                errors.append(
                    f"[run] {model_name}: expected {expected!r} in run SQL\n"
                    f"      file: {sql_file}\n"
                    f"      got (first 300 chars): {content[:300]!r}"
                )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target-path",
        default="target",
        help="dbt target directory (default: target)",
    )
    args = parser.parse_args()
    target = Path(args.target_path)

    all_errors: list[str] = []

    print("=== Manifest: sql_header config assignments ===")
    manifest_errors = check_manifest(target)
    for e in manifest_errors:
        print(f"  FAIL: {e}")
    if not manifest_errors:
        print("  OK")
    all_errors.extend(manifest_errors)

    print("\n=== Run SQL: sql_header statement placement ===")
    run_errors = check_run_sql(target)
    for e in run_errors:
        print(f"  FAIL: {e}")
    if not run_errors:
        print("  OK")
    all_errors.extend(run_errors)

    print()
    if all_errors:
        print(f"FAILED: {len(all_errors)} error(s)")
        sys.exit(1)
    else:
        print("SUCCESS: all checks passed")


if __name__ == "__main__":
    main()
