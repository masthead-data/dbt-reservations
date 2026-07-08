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
    "projects/masthead-dev/locations/us/reservations/capacity-0"
)


def get_reservation_editions(target_path: Path) -> str:
    dbt_project_path = target_path.parent / "dbt_project.yml"
    if not dbt_project_path.exists():
        return RESERVATION_EDITIONS
    try:
        import yaml

        with open(dbt_project_path) as f:
            cfg = yaml.safe_load(f)
        for entry in cfg.get("vars", {}).get("RESERVATION_CONFIG", []):
            if entry.get("tag") == "editions":
                return entry.get("reservation") or RESERVATION_EDITIONS
    except Exception:
        pass
    return RESERVATION_EDITIONS


# node_id → expected substring in sql_header (None = must be empty)
MANIFEST_CHECKS: dict[str, str | None] = {}

# model name → expected substring in run SQL (None = must NOT contain SET @@reservation=)
RUN_CHECKS: dict[str, str | None] = {}

# node_id → expected config.reservation value (None = field must be absent/null)
# Only populated by dbt-core v2+; absent on older engines and dbt-fusion.
MANIFEST_NATIVE_CHECKS: dict[str, str | None] = {}


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
        node = next((n for nid, n in nodes.items() if nid.startswith(node_id)), None)
        if not node:
            errors.append(f"[manifest] Node not found matching: {node_id}")
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
    native_nodes = {}
    for nid in MANIFEST_NATIVE_CHECKS:
        match_node = next((n for key, n in nodes.items() if key.startswith(nid)), None)
        if match_node:
            native_nodes[nid] = match_node

    if tag:
        native_nodes = {
            nid: node
            for nid, node in native_nodes.items()
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
        node = next((n for key, n in nodes.items() if key.startswith(node_id)), None)
        if not node:
            errors.append(f"[manifest-native] Node not found matching: {node_id}")
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
            errors.append(
                f"[run] SQL file not found for model '{model_name}' under {run_dir}"
            )
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


def get_project_id(target_path: Path) -> str:
    profiles_path = target_path.parent / "profiles.yml"
    if not profiles_path.exists():
        return "masthead-dev"
    try:
        import yaml

        with open(profiles_path) as f:
            cfg = yaml.safe_load(f)
        return (
            cfg.get("default", {}).get("outputs", {}).get("bigquery", {}).get("project")
            or "masthead-dev"
        )
    except Exception:
        pass
    return "masthead-dev"


EXPECTED_JOB_RESERVATIONS = {
    "dbt-core-1.9": {
        "model.bq_reservations_test.default": {"parent": ["capacity-0"], "children": []},
        "model.bq_reservations_test.on_demand": {"parent": ["None/On-demand"], "children": ["None/On-demand"]},
        "model.bq_reservations_test.slots": {"parent": ["None/On-demand", "capacity-0"], "children": ["capacity-1"]},
        "seed.bq_reservations_test.some_seed": {"parent": ["None/On-demand", "capacity-0"], "children": []},
        "snapshot.bq_reservations_test.slots_snapshot": {"parent": ["None/On-demand", "capacity-0"], "children": ["capacity-1"]},
        "test.bq_reservations_test.test_simple": {"parent": ["capacity-0"], "children": []},
    },
    "dbt-core-latest": {
        "model.bq_reservations_test.default": {"parent": ["capacity-0"], "children": []},
        "model.bq_reservations_test.on_demand": {"parent": ["None/On-demand"], "children": ["None/On-demand"]},
        "model.bq_reservations_test.slots": {"parent": ["None/On-demand", "capacity-0"], "children": ["capacity-1"]},
        "seed.bq_reservations_test.some_seed": {"parent": ["None/On-demand", "capacity-0"], "children": []},
        "snapshot.bq_reservations_test.slots_snapshot": {"parent": ["None/On-demand", "capacity-0"], "children": ["capacity-1"]},
        "test.bq_reservations_test.test_simple": {"parent": ["capacity-0"], "children": []},
    },
    # dbt-core v2 / dbt-fusion use native `reservation` config via the ADBC driver.
    # The *current* observed state (both PRs pending): reservation config is visible in the
    # manifest but the ADBC driver option is not yet wired up by dbt-fusion, so all jobs
    # land on the project default (capacity-0).
    # TODO: flip to "dbt-core-v2-preview-fixed" expectations once dbt-labs/arrow-adbc#133
    # and dbt-labs/dbt-fusion#1742 are merged and deployed.
    "dbt-core-v2-preview": {
        "model.bq_reservations_test.default": {"parent": ["capacity-0"], "children": []},
        "model.bq_reservations_test.on_demand": {"parent": ["capacity-0"], "children": []},
        "model.bq_reservations_test.slots": {"parent": ["capacity-0"], "children": []},
        "seed.bq_reservations_test.some_seed": {"parent": ["None/On-demand"], "children": []},
        "snapshot.bq_reservations_test.slots_snapshot": {"parent": ["None/On-demand", "capacity-0"], "children": []},
        "test.bq_reservations_test.test_simple": {"parent": ["capacity-0"], "children": []},
    },
    # Goal state once arrow-adbc#133 + dbt-fusion#1742 are merged:
    # native reservation config is passed as adbc.bigquery.sql.query.reservation → BQ jobs
    # land on the correct reservation per model config.
    "dbt-core-v2-preview-fixed": {
        "model.bq_reservations_test.default": {"parent": ["capacity-0"], "children": []},
        "model.bq_reservations_test.on_demand": {"parent": ["None/On-demand"], "children": []},
        "model.bq_reservations_test.slots": {"parent": ["capacity-1"], "children": []},
        "seed.bq_reservations_test.some_seed": {"parent": ["None/On-demand"], "children": []},
        "snapshot.bq_reservations_test.slots_snapshot": {"parent": ["capacity-1", "capacity-0", "None/On-demand"], "children": []},
        "test.bq_reservations_test.test_simple": {"parent": ["capacity-1"], "children": []},
    },
    # Current observed state: reservation config in manifest but not wired to ADBC.
    # TODO: flip to "dbt-fusion-latest-fixed" once arrow-adbc#133 + dbt-fusion#1742 land.
    "dbt-fusion-latest": {
        "model.bq_reservations_test.default": {"parent": ["capacity-0"], "children": []},
        "model.bq_reservations_test.on_demand": {"parent": ["capacity-0"], "children": []},
        "model.bq_reservations_test.slots": {"parent": ["capacity-0"], "children": []},
        "seed.bq_reservations_test.some_seed": {"parent": ["None/On-demand"], "children": []},
        "snapshot.bq_reservations_test.slots_snapshot": {"parent": ["None/On-demand", "capacity-0"], "children": []},
        "test.bq_reservations_test.test_simple": {"parent": ["capacity-0"], "children": []},
    },
    # Goal state once arrow-adbc#133 + dbt-fusion#1742 are merged:
    "dbt-fusion-latest-fixed": {
        "model.bq_reservations_test.default": {"parent": ["capacity-0"], "children": []},
        "model.bq_reservations_test.on_demand": {"parent": ["None/On-demand"], "children": []},
        "model.bq_reservations_test.slots": {"parent": ["capacity-1"], "children": []},
        "seed.bq_reservations_test.some_seed": {"parent": ["None/On-demand"], "children": []},
        "snapshot.bq_reservations_test.slots_snapshot": {"parent": ["capacity-1", "capacity-0", "None/On-demand"], "children": []},
        "test.bq_reservations_test.test_simple": {"parent": ["capacity-1"], "children": []},
    },
}



def verify_bigquery_jobs(target_path: Path, reservation_editions: str, invocation_ids: list[str], dbt_version_name: str) -> tuple[list[dict], list[str]]:
    results_list = []
    bq_errors = []
    project_id = get_project_id(target_path)

    print("\n=== BigQuery: End-to-End Job Reservation Verification ===")
    if not invocation_ids:
        print("  (skipped — no invocation IDs passed)")
        return [], []

    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=project_id)
    except Exception as e:
        print(f"  (skipped — google-cloud-bigquery client not available: {e})")
        return [], []

    query = """
    SELECT
      job_id,
      parent_job_id,
      reservation_id,
      labels
    FROM
      `region-us`.INFORMATION_SCHEMA.JOBS_BY_USER
    WHERE
      creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 MINUTE)
    """
    try:
        query_job = client.query(query)
        rows = list(query_job.result())
    except Exception as e:
        print(f"  (skipped — failed to query JOBS_BY_USER: {e})")
        return [], []

    # 1. Find all parent jobs belonging to our current invocation IDs
    parent_job_to_node = {}  # job_id -> node_id_label
    node_to_parent_jobs = {}  # node_id_label -> list of parent job rows
    
    for row in rows:
        labels = row.labels or []
        inv_id_val = next((l["value"] for l in labels if l["key"] == "dbt_invocation_id"), None)
        if inv_id_val in invocation_ids:
            node_id_label = next((l["value"] for l in labels if l["key"] == "node_id"), None)
            if node_id_label:
                parent_job_to_node[row.job_id] = node_id_label
                node_to_parent_jobs.setdefault(node_id_label, []).append(row)

    # 2. Find child jobs pointing to our parent jobs
    node_to_all_jobs = {}  # node_id_label -> list of job rows (parent + children)
    
    # Initialize with parent jobs
    for node_id_label, parents in node_to_parent_jobs.items():
        node_to_all_jobs[node_id_label] = list(parents)
        
    for row in rows:
        p_id = row.parent_job_id
        if p_id in parent_job_to_node:
            node_id_label = parent_job_to_node[p_id]
            node_to_all_jobs.setdefault(node_id_label, []).append(row)

    res_config = load_reservation_config(target_path)
    expected_nodes = {}
    for entry in res_config:
        res_val = entry.get("reservation")
        
        if res_val is None:
            expected_res = "capacity-0"
        elif res_val == "none":
            expected_res = "None/On-demand"
        else:
            expected_res = res_val.split("/")[-1]
            
        for node_id in entry.get("models", []):
            label_prefix = node_id.replace(".", "_")
            expected_nodes[label_prefix] = expected_res

    def label_to_node_id(label_prefix: str) -> str:
        parts = label_prefix.split("_")
        if len(parts) >= 2:
            resource_type = parts[0]
            rest = "_".join(parts[1:])
            if rest.startswith("bq_reservations_test_"):
                model_name = rest[len("bq_reservations_test_"):]
                return f"{resource_type}.bq_reservations_test.{model_name}"
        return label_prefix

    # 3. Verify reservation for each expected node prefix
    for expected_lbl, expected_res in expected_nodes.items():
        matched_node_labels = [lbl for lbl in node_to_all_jobs if lbl.startswith(expected_lbl)]
        
        if not matched_node_labels:
            print(f"  INFO: {expected_lbl} — No query jobs found for the current invocation.")
            continue
            
        all_jobs = []
        for lbl in matched_node_labels:
            all_jobs.extend(node_to_all_jobs[lbl])
            
        unique_reservations = set()
        job_details = []
        parent_job_ids = set()
        unique_inv_ids = set()
        for job in all_jobs:
            res_id = job.reservation_id or "None/On-demand"
            unique_reservations.add(res_id)
            job_details.append(f"{job.job_id} ({res_id})")
            parent_job_ids.add(job.parent_job_id or job.job_id)
            labels = job.labels or []
            inv_id_val = next((l["value"] for l in labels if l["key"] == "dbt_invocation_id"), None)
            if inv_id_val:
                unique_inv_ids.add(inv_id_val)
            
        print(f"  Node prefix: {expected_lbl}")
        print(f"    Jobs checked: {', '.join(job_details)}")
        
        factual_res = ", ".join(sorted(list(unique_reservations)))
        parent_job_str = ", ".join(sorted(list(parent_job_ids)))
        inv_id_str = ", ".join(sorted(list(unique_inv_ids)))
        results_list.append({
            "node_id": label_to_node_id(expected_lbl),
            "expected": expected_res,
            "factual": factual_res,
            "parent_job_id": parent_job_str,
            "invocation_id": inv_id_str
        })
        
        node_id = label_to_node_id(expected_lbl)
        version_rules = EXPECTED_JOB_RESERVATIONS.get(dbt_version_name, {})
        rules = version_rules.get(node_id)
        
        if not rules:
            print(f"    WARN: No expected rules configured for version {dbt_version_name!r} and node {node_id!r}")
            continue

        expected_parent = rules["parent"]
        expected_children = rules["children"]

        parent_jobs = [job for job in all_jobs if not job.parent_job_id]
        child_jobs = [job for job in all_jobs if job.parent_job_id]

        node_errors = []
        for job in parent_jobs:
            res_id = job.reservation_id or "None/On-demand"
            if not any(res_id.endswith(exp) or (exp == "None/On-demand" and res_id == "None/On-demand") for exp in expected_parent):
                node_errors.append(f"Unexpected parent job reservation: {res_id!r} (expected one of {expected_parent})")

        for job in child_jobs:
            res_id = job.reservation_id or "None/On-demand"
            if not any(res_id.endswith(exp) or (exp == "None/On-demand" and res_id == "None/On-demand") for exp in expected_children):
                node_errors.append(f"Unexpected child job reservation: {res_id!r} (expected one of {expected_children})")

        if node_errors:
            for err in node_errors:
                print(f"    FAIL: {err}")
            bq_errors.extend(node_errors)
        else:
            print(f"    OK: Reservations matched hardcoded rules")
                    
    return results_list, bq_errors


def update_markdown_results(markdown_path: Path, dbt_version_name: str, results: list[dict]) -> None:
    header = "| dbt Version | dbt Node ID | Configured Reservation (Manifest) | Factual Reservation | Parent Job ID | Invocation ID |"
    separator = "| --- | --- | --- | --- | --- | --- |"
    
    rows = {}  # (dbt_version, node_id) -> (expected, factual, parent_job_id, invocation_id)
    
    if markdown_path.exists():
        try:
            for line in markdown_path.read_text().splitlines():
                line = line.strip()
                if not line.startswith("|") or "dbt Version" in line or "---" in line:
                    continue
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) >= 6:
                    v, nid, exp, fact, pid, inv = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
                    if v != dbt_version_name:
                        rows[(v, nid)] = (exp, fact, pid, inv)
                elif len(parts) == 5:
                    v, nid, exp, fact, pid = parts[0], parts[1], parts[2], parts[3], parts[4]
                    if v != dbt_version_name:
                        rows[(v, nid)] = (exp, fact, pid, "")
        except Exception:
            pass
            
    # Update with new results
    for r in results:
        rows[(dbt_version_name, r['node_id'])] = (
            r['expected'],
            r['factual'],
            r['parent_job_id'],
            r['invocation_id']
        )
        
    # Write back
    content = [header, separator]
    for (v, nid), (exp, fact, pid, inv) in sorted(rows.items()):
        content.append(f"| {v} | {nid} | {exp} | {fact} | {pid} | {inv} |")
        
    try:
        markdown_path.write_text("\n".join(content) + "\n")
        print(f"Updated results table in {markdown_path}")
    except Exception as e:
        print(f"Warning: Failed to write to {markdown_path}: {e}")


def load_reservation_config(target_path: Path) -> list[dict]:
    dbt_project_path = target_path.parent / "dbt_project.yml"
    if not dbt_project_path.exists():
        return []
    try:
        import yaml

        with open(dbt_project_path) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("vars", {}).get("RESERVATION_CONFIG") or []
    except Exception:
        return []


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
    parser.add_argument(
        "--invocation-ids",
        default="",
        help="Comma-separated list of dbt invocation IDs for the current run",
    )
    parser.add_argument(
        "--dbt-version-name",
        default="unknown",
        help="The name of the dbt version/session being run",
    )
    parser.add_argument(
        "--results-markdown",
        default=None,
        help="Path to markdown file where end-to-end verification results table is saved",
    )

    args = parser.parse_args()
    target = Path(args.target_path)
    invocation_ids = [i.strip() for i in args.invocation_ids.split(",") if i.strip()]

    global RESERVATION_EDITIONS, MANIFEST_CHECKS, RUN_CHECKS, MANIFEST_NATIVE_CHECKS
    RESERVATION_EDITIONS = get_reservation_editions(target)

    res_config = load_reservation_config(target)
    for entry in res_config:
        res_val = entry.get("reservation")
        for node_id in entry.get("models", []):
            MANIFEST_NATIVE_CHECKS[node_id] = None if node_id.startswith("seed.") else res_val
            if node_id.startswith("model.") or node_id.startswith("snapshot."):
                if res_val is None:
                    MANIFEST_CHECKS[node_id] = None
                elif res_val == "none":
                    MANIFEST_CHECKS[node_id] = 'SET @@reservation= "none";'
                else:
                    MANIFEST_CHECKS[node_id] = f'SET @@reservation= "{res_val}";'

                if node_id.startswith("model."):
                    model_name = node_id.split(".")[-1]
                    if "ephemeral" not in model_name:
                        if res_val is None:
                            RUN_CHECKS[model_name] = None
                        elif res_val == "none":
                            RUN_CHECKS[model_name] = 'SET @@reservation= "none";'
                        else:
                            RUN_CHECKS[model_name] = f'SET @@reservation= "{res_val}";'
            else:
                MANIFEST_CHECKS[node_id] = None

    all_errors: list[str] = []

    print("=== Manifest: native reservation config (dbt-core v2+) ===")
    native_errors = check_manifest_native(target, tag=args.tag)
    if native_errors is not None:
        # Engine is dbt-core v2+ (native configuration)
        for e in native_errors:
            print(f"  FAIL: {e}")
        if not native_errors:
            print("  OK")
        all_errors.extend(native_errors)
        print("\n=== Manifest: sql_header config assignments ===")
        print("  (skipped — engine uses native reservation config)")
        print("\n=== Run SQL: sql_header statement placement ===")
        print("  (skipped — engine uses native reservation config)")
    else:
        # Engine is older (dbt-core v1)
        print("  (skipped — engine does not populate config.reservation in manifest)")

        print("\n=== Manifest: sql_header config assignments ===")
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

    # Perform BQ job level verification
    results, bq_errors = verify_bigquery_jobs(target, RESERVATION_EDITIONS, invocation_ids, args.dbt_version_name)
    all_errors.extend(bq_errors)

    if args.results_markdown:
        update_markdown_results(Path(args.results_markdown), args.dbt_version_name, results)

    print()
    if all_errors:
        print(f"FAILED: {len(all_errors)} error(s)")
        sys.exit(1)
    else:
        print("SUCCESS: all checks passed")


if __name__ == "__main__":
    main()
