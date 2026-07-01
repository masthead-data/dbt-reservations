#!/usr/bin/env python3
"""
Verify dbt integration test output.

Checks three things:
  1. manifest.json — sql_header config was resolved correctly by the macro (after `dbt compile`)
  2. target/run/ SQL files — sql_header statement is physically present in run DDL (after `dbt run`)
  3. manifest.json — native `reservation` config attribute (dbt-core v2+ only; skipped on older
     engines that don't populate config.reservation)

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

# node_id → expected config.reservation value (None = field must be absent/null)
# Only populated by dbt-core v2+; absent on older engines and dbt-fusion.
MANIFEST_NATIVE_CHECKS: dict[str, str | None] = {
    "model.bq_reservations_sample.slots_native": RESERVATION_EDITIONS,
    "model.bq_reservations_sample.on_demand_native": "none",
    "model.bq_reservations_sample.default_native": None,  # no reservation → absent/null
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


def check_manifest(target: Path, tag: str | None = None) -> list[str]:
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
        if tag and tag not in node.get("tags", []):
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


def check_manifest_native(target: Path, tag: str | None = None) -> list[str] | None:
    """Check native `reservation` config in manifest nodes (dbt-core v2+ only).

    Returns None when the engine doesn't populate config.reservation at all
    (graceful skip), or a list of error strings (empty = all OK).
    """
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        return [f"manifest.json not found at {manifest_path}"]

    nodes = json.loads(manifest_path.read_text()).get("nodes", {})

    # Detect whether this engine populates config.reservation at all.
    # If none of the native nodes have the key, assume an older engine and skip.
    native_nodes = {nid: nodes.get(nid) for nid in MANIFEST_NATIVE_CHECKS}
    if tag:
        native_nodes = {
            nid: node for nid, node in native_nodes.items()
            if node and tag in node.get("tags", [])
        }

    has_any = any(
        node is not None and "reservation" in node.get("config", {})
        for node in native_nodes.values()
    )
    if not has_any:
        return None  # signal: skip gracefully

    errors = []
    for node_id, expected in MANIFEST_NATIVE_CHECKS.items():
        node = nodes.get(node_id)
        if not node:
            errors.append(f"[manifest-native] Node not found: {node_id}")
            continue
        actual = node.get("config", {}).get("reservation")  # None if absent
        if expected is None:
            if actual is not None:
                errors.append(
                    f"[manifest-native] {node_id}: expected no reservation, got: {actual!r}"
                )
        else:
            if actual != expected:
                errors.append(
                    f"[manifest-native] {node_id}: expected {expected!r}, got: {actual!r}"
                )
    return errors


def check_run_sql(target: Path, tag: str | None = None) -> list[str]:
    errors = []
    run_dir = target / "run"
    if not run_dir.exists():
        return [f"target/run/ not found at {run_dir} — did you run `dbt run`?"]

    # Read manifest to filter models by tag if specified
    manifest_path = target / "manifest.json"
    nodes = {}
    if manifest_path.exists():
        nodes = json.loads(manifest_path.read_text()).get("nodes", {})

    for model_name, expected in RUN_CHECKS.items():
        node = next((n for n in nodes.values() if n.get("name") == model_name), None)
        if tag and node and tag not in node.get("tags", []):
            continue

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
            # The SET statement must appear as a SQL header — i.e. BEFORE the first
            # DDL keyword (CREATE/INSERT/MERGE). Finding it only inside the SELECT body
            # (e.g. as a string literal column value) is a false positive.
            import re
            ddl_match = re.search(r"\b(CREATE|INSERT|MERGE)\b", content, re.IGNORECASE)
            ddl_pos = ddl_match.start() if ddl_match else len(content)
            header_section = content[:ddl_pos]
            if expected not in header_section:
                errors.append(
                    f"[run] {model_name}: expected {expected!r} as a SQL header (before DDL)\n"
                    f"      file: {sql_file}\n"
                    f"      header section (first {ddl_pos} chars): {header_section[:300]!r}"
                )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target-path",
        default="target",
        help="dbt target directory (default: target)",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Filter verification checks to only models matching this tag",
    )

    args = parser.parse_args()
    target = Path(args.target_path)

    all_errors: list[str] = []

    print("=== Manifest: sql_header config assignments ===")
    manifest_errors = check_manifest(target, tag=args.tag)
    for e in manifest_errors:
        print(f"  FAIL: {e}")
    if not manifest_errors:
        print("  OK")
    all_errors.extend(manifest_errors)

    print("\n=== Run SQL: sql_header statement placement ===")
    run_errors = check_run_sql(target, tag=args.tag)
    for e in run_errors:
        print(f"  FAIL: {e}")
    if not run_errors:
        print("  OK")
    all_errors.extend(run_errors)

    print("\n=== Manifest: native reservation config (dbt-core v2+) ===")
    native_errors = check_manifest_native(target, tag=args.tag)
    if native_errors is None:
        print("  (skipped — engine does not populate config.reservation in manifest)")
    else:
        for e in native_errors:
            print(f"  FAIL: {e}")
        if not native_errors:
            print("  OK")
        all_errors.extend(native_errors)

    print()
    if all_errors:
        print(f"FAILED: {len(all_errors)} error(s)")
        sys.exit(1)
    else:
        print("SUCCESS: all checks passed")


if __name__ == "__main__":
    main()
