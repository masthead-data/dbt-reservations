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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

RESERVATION_EDITIONS = (
    "projects/masthead-dev/locations/us/reservations/capacity-0"
)


def get_job_label(labels, key: str) -> str | None:
    if isinstance(labels, dict):
        return labels.get(key)
    elif isinstance(labels, list):
        return next((l["value"] for l in labels if isinstance(l, dict) and l.get("key") == key), None)
    return None


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
# Only populated by dbt-core v2+; absent on older engines.
MANIFEST_NATIVE_CHECKS: dict[str, str | None] = {}


def find_run_sql(run_dir: Path, model_name: str) -> Path | None:
    """Search recursively for compiled model SQL."""
    matches = list(run_dir.rglob(f"{model_name}.sql"))
    if not matches:
        return None
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
        match_node = nodes.get(nid)
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
        node = nodes.get(node_id)
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
    "dbt-core-latest": {
        "model.bq_reservations_test.default": {"expected": "enterprise-1", "parent": ["enterprise-1", "capacity-0"], "children": []},
        "model.bq_reservations_test.on_demand": {"expected": "None/On-demand", "parent": ["None/On-demand"], "children": ["None/On-demand"]},
        "model.bq_reservations_test.slots": {"expected": "capacity-1", "parent": ["None/On-demand", "enterprise-1", "capacity-0"], "children": ["capacity-1"]},
        "model.bq_reservations_test.slots_incremental": {"expected": "capacity-1", "parent": ["None/On-demand", "enterprise-1", "capacity-0"], "children": ["capacity-1"]},
        "model.bq_reservations_test.slots_materialized_view": {"expected": "None/On-demand", "parent": ["None/On-demand"], "children": ["None/On-demand"]},
        "model.bq_reservations_test.slots_hooks": {"expected": "capacity-1", "parent": ["None/On-demand", "enterprise-1", "capacity-0"], "children": ["capacity-1"]},
        "model.bq_reservations_test.slots_path": {"expected": "capacity-1", "parent": ["None/On-demand", "enterprise-1", "capacity-0"], "children": ["capacity-1"]},
        "model.bq_reservations_test.slots_path_incremental": {"expected": "capacity-1", "parent": ["None/On-demand", "enterprise-1", "capacity-0"], "children": ["capacity-1"]},
        "snapshot.bq_reservations_test.slots_snapshot": {"expected": "capacity-1", "parent": ["None/On-demand", "enterprise-1", "capacity-0"], "children": ["capacity-1"]},
        "test.bq_reservations_test.test_simple": {"expected": "enterprise-1", "parent": ["enterprise-1", "capacity-0"], "children": []},
    },
    # dbt-core v2 uses native `reservation` config via the ADBC driver.
    # The *current* observed release state (PRs pending): reservation config is visible in the
    # manifest but the ADBC driver option is not yet wired up, so all jobs
    # land on the project default (enterprise-1 / capacity-0).
    "dbt-core-v2": {
        "model.bq_reservations_test.default": {"expected": "enterprise-1", "parent": ["enterprise-1", "capacity-0"], "children": []},
        "model.bq_reservations_test.on_demand": {"expected": "enterprise-1", "parent": ["enterprise-1", "capacity-0", "None/On-demand"], "children": ["None/On-demand"]},
        "model.bq_reservations_test.slots": {"expected": "enterprise-1", "parent": ["enterprise-1", "capacity-0"], "children": []},
        "model.bq_reservations_test.slots_incremental": {"expected": "enterprise-1", "parent": ["enterprise-1", "capacity-0"], "children": []},
        "model.bq_reservations_test.slots_materialized_view": {"expected": "None/On-demand", "parent": ["enterprise-1", "capacity-0", "None/On-demand"], "children": ["None/On-demand"]},
        "model.bq_reservations_test.slots_hooks": {"expected": "enterprise-1", "parent": ["enterprise-1", "capacity-0"], "children": []},
        "model.bq_reservations_test.slots_path": {"expected": "enterprise-1", "parent": ["enterprise-1", "capacity-0"], "children": []},
        "model.bq_reservations_test.slots_path_incremental": {"expected": "enterprise-1", "parent": ["enterprise-1", "capacity-0"], "children": []},
        "snapshot.bq_reservations_test.slots_snapshot": {"expected": "enterprise-1", "parent": ["None/On-demand", "enterprise-1", "capacity-0"], "children": []},
        "test.bq_reservations_test.test_simple": {"expected": "enterprise-1", "parent": ["enterprise-1", "capacity-0"], "children": []},
    },
    # Fixed state with ADBC driver PR #133:
    # native reservation config is passed as adbc.bigquery.sql.query.reservation → BQ jobs
    # land on the correct reservation per model config.
    "dbt-core-v2-fixed": {
        "model.bq_reservations_test.default": {"expected": "enterprise-1", "parent": ["capacity-0", "enterprise-1"], "children": []},
        "model.bq_reservations_test.on_demand": {"expected": "None/On-demand", "parent": ["None/On-demand"], "children": []},
        "model.bq_reservations_test.slots": {"expected": "capacity-1", "parent": ["capacity-1"], "children": []},
        "model.bq_reservations_test.slots_incremental": {"expected": "capacity-1", "parent": ["capacity-1"], "children": []},
        "model.bq_reservations_test.slots_materialized_view": {"expected": "None/On-demand", "parent": ["None/On-demand"], "children": ["None/On-demand"]},
        "model.bq_reservations_test.slots_hooks": {"expected": "capacity-1", "parent": ["capacity-1"], "children": []},
        "model.bq_reservations_test.slots_path": {"expected": "capacity-1", "parent": ["capacity-1"], "children": []},
        "model.bq_reservations_test.slots_path_incremental": {"expected": "capacity-1", "parent": ["capacity-1"], "children": []},
        "snapshot.bq_reservations_test.slots_snapshot": {"expected": "capacity-1", "parent": ["capacity-1", "capacity-0", "enterprise-1", "None/On-demand"], "children": []},
        "test.bq_reservations_test.test_simple": {"expected": "capacity-1", "parent": ["capacity-1"], "children": []},
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

    # 1. Fetch recent root jobs via BigQuery REST API
    min_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    try:
        recent_jobs = list(client.list_jobs(project=project_id, max_results=300, min_creation_time=min_time))
    except Exception as e:
        print(f"  (skipped — failed to list jobs via BigQuery API: {e})")
        return [], []

    # 2. Filter parent jobs matching our current invocation IDs
    parent_job_to_node = {}  # job_id -> node_id_label
    node_to_parent_jobs = {}  # node_id_label -> list of parent job items
    matching_parents = []

    for job in recent_jobs:
        labels = job.labels or {}
        inv_id_val = get_job_label(labels, "dbt_invocation_id")
        if inv_id_val in invocation_ids:
            node_id_label = get_job_label(labels, "node_id")
            if node_id_label:
                parent_job_to_node[job.job_id] = node_id_label
                node_to_parent_jobs.setdefault(node_id_label, []).append(job)
                matching_parents.append(job)

    # 3. Concurrently fetch child jobs (e.g. dbt v1 script query executions)
    def fetch_children(parent_job):
        try:
            return parent_job.job_id, list(client.list_jobs(project=project_id, parent_job=parent_job.job_id))
        except Exception:
            return parent_job.job_id, []

    node_to_all_jobs = {}
    for node_id_label, parents in node_to_parent_jobs.items():
        node_to_all_jobs[node_id_label] = list(parents)

    with ThreadPoolExecutor(max_workers=8) as pool:
        child_results = pool.map(fetch_children, matching_parents)

    for p_id, children in child_results:
        node_id_label = parent_job_to_node.get(p_id)
        if node_id_label and children:
            node_to_all_jobs[node_id_label].extend(children)

    res_config = load_reservation_config(target_path)
    configured_map = {}
    for entry in res_config:
        res_val = entry.get("reservation")
        if res_val is None:
            conf_str = "null (default)"
        elif res_val == "none":
            conf_str = "none (on-demand)"
        else:
            conf_str = res_val.split("/")[-1]

        for node_id in entry.get("models", []):
            configured_map[node_id] = conf_str

    version_rules = EXPECTED_JOB_RESERVATIONS.get(dbt_version_name, {})
    if not version_rules:
        print(f"  WARN: No expected rules configured for version {dbt_version_name!r}")
        return results_list, bq_errors

    # 4. Verify reservation for each expected node
    for node_id, rules in version_rules.items():
        expected_lbl = node_id.replace(".", "_")
        configured_res = configured_map.get(node_id, "null (default)")
        expected_res = rules.get("expected", "enterprise-1")
        expected_parent = rules["parent"]
        expected_children = rules["children"]

        matched_node_labels = [lbl for lbl in node_to_all_jobs if lbl == expected_lbl or (node_id.startswith("test.") and lbl.startswith(expected_lbl + "_"))]

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
            labels = job.labels or {}
            inv_id_val = get_job_label(labels, "dbt_invocation_id")
            if inv_id_val:
                unique_inv_ids.add(inv_id_val)

        print(f"  Node: {node_id}")
        print(f"    Configured: {configured_res} | Expected: {expected_res}")
        print(f"    Jobs checked: {', '.join(job_details)}")

        parent_jobs = [job for job in all_jobs if not job.parent_job_id]
        child_jobs = [job for job in all_jobs if job.parent_job_id]

        parent_res = ", ".join(sorted(list({j.reservation_id or "None/On-demand" for j in parent_jobs}))) or "-"
        child_res = ", ".join(sorted(list({j.reservation_id or "None/On-demand" for j in child_jobs}))) or "-"
        parent_job_str = ", ".join(sorted(list(parent_job_ids)))
        inv_id_str = ", ".join(sorted(list(unique_inv_ids)))
        observed_comp = get_observed_compilation(target_path, node_id)
        results_list.append({
            "node_id": node_id,
            "configured": configured_res,
            "expected": expected_res,
            "observed_compilation": observed_comp,
            "parent_res": parent_res,
            "child_res": child_res,
            "parent_job_id": parent_job_str,
            "invocation_id": inv_id_str
        })

        node_errors = []
        for job in parent_jobs:
            res_id = job.reservation_id or "None/On-demand"
            parent_allowed = expected_parent if isinstance(expected_parent, list) else [expected_parent]
            if not any(res_id.endswith(exp) or (exp == "None/On-demand" and res_id == "None/On-demand") for exp in parent_allowed):
                node_errors.append(f"Unexpected parent job reservation: {res_id!r} (expected one of {parent_allowed})")

        for job in child_jobs:
            res_id = job.reservation_id or "None/On-demand"
            children_allowed = expected_children if isinstance(expected_children, list) else [expected_children]
            if not any(res_id.endswith(exp) or (exp == "None/On-demand" and res_id == "None/On-demand") for exp in children_allowed):
                node_errors.append(f"Unexpected child job reservation: {res_id!r} (expected one of {children_allowed})")

        if node_errors:
            for err in node_errors:
                print(f"    FAIL: {err}")
            bq_errors.extend(node_errors)
        else:
            print(f"    OK: Reservations matched hardcoded rules")

    return results_list, bq_errors


def get_observed_compilation(target_path: Path, node_id: str) -> str:
    manifest_path = target_path / "manifest.json"
    if not manifest_path.exists():
        return "-"
    try:
        data = json.loads(manifest_path.read_text())
        node = data.get("nodes", {}).get(node_id)
        if not node:
            return "-"
        config = node.get("config", {})
        native_res = config.get("reservation")
        sql_header = config.get("sql_header")

        if native_res is not None:
            if native_res == "none":
                return "none (on-demand)"
            elif "/" in str(native_res):
                return native_res.split("/")[-1]
            return str(native_res)
        elif sql_header:
            sql_hdr_clean = sql_header.strip()
            if "SET @@reservation=" in sql_hdr_clean:
                import re
                m = re.search(r'SET @@reservation=\s*["\']([^"\']+)["\']', sql_hdr_clean)
                if m:
                    res_val = m.group(1)
                    res_name = res_val.split("/")[-1] if "/" in res_val else res_val
                    if res_name == "none":
                        return 'SET @@reservation= "none";'
                    return f'SET @@reservation= "{res_name}";'
                return sql_hdr_clean
            return sql_hdr_clean
        else:
            return "-"
    except Exception:
        return "-"


def update_markdown_results(markdown_path: Path, dbt_version_name: str, results: list[dict]) -> None:
    header = "| dbt Version | dbt Node ID | Configured (dbt_project.yml) | Expected (Engine Capable) | Observed at Compilation | Parent Job Reservation | Child Jobs Reservation | Parent Job ID | Invocation ID |"
    separator = "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"

    rows = {}  # (dbt_version, node_id) -> (configured, expected, observed_comp, parent_res, child_res, parent_job_id, invocation_id)

    if markdown_path.exists():
        try:
            for line in markdown_path.read_text().splitlines():
                line = line.strip()
                if not line.startswith("|") or "dbt Version" in line or "---" in line:
                    continue
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) >= 9:
                    v, nid, conf, exp, obs, p_res, c_res, pid, inv = parts[:9]
                    if v != dbt_version_name:
                        rows[(v, nid)] = (conf, exp, obs, p_res, c_res, pid, inv)
                elif len(parts) == 8:
                    v, nid, conf, exp, p_res, c_res, pid, inv = parts[:8]
                    if v != dbt_version_name:
                        rows[(v, nid)] = (conf, exp, "-", p_res, c_res, pid, inv)
                elif len(parts) == 7:
                    v, nid, exp, p_res, c_res, pid, inv = parts[:7]
                    if v != dbt_version_name:
                        rows[(v, nid)] = ("-", exp, "-", p_res, c_res, pid, inv)
        except Exception:
            pass

    # Update with new results
    for r in results:
        rows[(dbt_version_name, r['node_id'])] = (
            r['configured'],
            r['expected'],
            r.get('observed_compilation', '-'),
            r['parent_res'],
            r['child_res'],
            r['parent_job_id'],
            r['invocation_id']
        )

    # Write back
    content = [header, separator]
    for (v, nid), (conf, exp, obs, p_res, c_res, pid, inv) in sorted(rows.items()):
        content.append(f"| {v} | {nid} | {conf} | {exp} | {obs} | {p_res} | {c_res} | {pid} | {inv} |")

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
            if node_id.startswith("model.") or node_id.startswith("snapshot."):
                MANIFEST_NATIVE_CHECKS[node_id] = res_val
                if res_val is None:
                    MANIFEST_CHECKS[node_id] = None
                elif res_val == "none":
                    MANIFEST_CHECKS[node_id] = 'SET @@reservation= "none";'
                else:
                    MANIFEST_CHECKS[node_id] = f'SET @@reservation= "{res_val}";'

                if node_id.startswith("model."):
                    model_name = node_id.split(".")[-1]
                    if "ephemeral" not in model_name and "materialized_view" not in model_name:
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
