# Test Cases & Testing Matrix

This repository uses a **Two-Tier Testing Architecture** to guarantee correctness across dbt versions, materialization types, and BigQuery execution engines.

---

## 1. Two-Tier Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Tier 1: Static Macro & Compile Matrix (Fast, Offline, No GCP Auth)      │
│ ----------------------------------------------------------------------- │
│ • Jinja Macro Unit Tests (Pure Jinja2 simulation with pytest)           │
│ • dbt Compile Matrix (`dbt compile` across dbt-core latest and v2)      │
│ • Manifest Validation (`manifest.json` config inspection)               │
│ • Triggered: Every PR and commit in CI                                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────────────┐
│ Tier 2: End-to-End BigQuery Job Verification (Live GCP Execution)       │
│ ----------------------------------------------------------------------- │
│ • Live `dbt build` against BigQuery (`masthead-dev`)                    │
│ • Physical DDL Verification (`target/run/*.sql` headers)                │
│ • BigQuery Job API / Control Plane Verification                         │
│ • Asserts parent script & child query slot routing                      │
│ • Triggered: Release tags, Nightly, or manual dispatch                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Test Matrix Dimensions

| Dimension | Scope & Options |
| :--- | :--- |
| **Resource Type** | `model`, `snapshot`, `singular test`, `generic test`, `hook` *(seeds & views excluded — metadata-only/shared ingestion)* |
| **Materialization** | `table`, `incremental`, `ephemeral`, `materialized_view`, `snapshot` |
| **File Format** | `.sql` (Jinja SQL), `.yml` (Properties & Tests) |
| **Assignment Target** | Dedicated Slots (`projects/.../reservations/capacity-X`), On-Demand (`none`), Default Project (`null`) |
| **Engine / Compatibility** | `dbt-core` latest (`>=1.12.0`), `dbt-core-v2-fixed` (local fixed build) |

---

## 3. Integration Test Cases (`integration_tests/`)

| Test Node | File | Type / Materialization | Target Reservation | Expected `assign_from_config` (dbt v1) | Expected `get_name_from_config` (dbt v2+) | Expected Execution (BQ Job) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `slots` | `models/slots.sql` | `table` | `.../capacity-1` | `SET @@reservation= ".../capacity-1";` | `.../capacity-1` | `capacity-1` (Child CTAS) |
| `slots_incremental` | `models/slots_incremental.sql` | `incremental` | `.../capacity-1` | `SET @@reservation= ".../capacity-1";` | `.../capacity-1` | `capacity-1` (Child CTAS/Merge) |
| `slots_materialized_view` | `models/slots_materialized_view.sql` | `materialized_view` | `.../enterprise-0` | `None` *(v1 ignores `sql_header`)* | `.../enterprise-0` | `None/On-demand` (v1) / `enterprise-0` (v2+ goal) |
| `slots_path` | `models/path/slots_path.sql` | `table` | `.../capacity-1` | `SET @@reservation= ".../capacity-1";` | `.../capacity-1` | `capacity-1` (Child CTAS) |
| `slots_path_incremental` | `models/path/slots_path_incremental.sql` | `incremental` | `.../capacity-1` | `SET @@reservation= ".../capacity-1";` | `.../capacity-1` | `capacity-1` (Child CTAS/Merge) |
| `slots_ephemeral` | `models/path/slots_ephemeral.sql` | `ephemeral` | `.../capacity-1` | `SET @@reservation= ".../capacity-1";` | `.../capacity-1` | Inlined CTE (no separate job) |
| `slots_hooks` | `models/slots_hooks.sql` | `table` (hooks) | `.../capacity-1` | `SET @@reservation= ".../capacity-1";` | `.../capacity-1` | `capacity-1` (Child CTAS) |
| `default` | `models/default.sql` | `table` | `null` (default) | `""` | `None` | `enterprise-1` (project default) |
| `on_demand` | `models/on_demand.sql` | `table` | `none` (on-demand) | `SET @@reservation= "none";` | `none` | `None/On-demand` |
| `slots_snapshot` | `snapshots/slots_snapshot.sql` | `snapshot` | `.../capacity-1` | `SET @@reservation= ".../capacity-1";` | `.../capacity-1` | `capacity-1` (Child Merge) |
| `test_simple` | `tests/test_simple.sql` | Singular Test | `.../capacity-1` | `None` *(v1 test runner ignores header)* | `.../capacity-1` | `enterprise-1` (v1 default) / `capacity-1` (v2+ goal) |
| `unique_slots_model_id` | `models/schema.yml` | Generic Test | Inherited | `""` | `None` | `enterprise-1` (project default) |
| `not_null_slots_model_id` | `models/schema.yml` | Generic Test | Inherited | `""` | `None` | `enterprise-1` (project default) |

---

## 4. Running the Tests

### Tier 1: Local Unit & Manifest Tests
```bash
# Run standalone macro unit tests (no dbt install or GCP credentials required)
pytest -v

# Or via nox
nox -s unit
```

### Tier 1: Local Compile Verification
```bash
cd integration_tests
dbt compile
pytest ../tests/test_manifest_structure.py
```

### Tier 2: End-to-End Live Integration Tests
```bash
# Run integration test across the full version matrix against BigQuery
make integration-test
```
