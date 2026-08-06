# Centralized Reservation Management for Enterprise Teams

This guide explains how Enterprise Platform Teams can centrally manage BigQuery compute reservation assignments across tens or hundreds of downstream dbt projects using **dbt Macro Dispatch**.

---

## Overview & Benefits

In enterprise organizations, model-to-reservation assignments are often managed by a central **Platform Team**, while individual **Data Teams** own their respective dbt projects. 

Instead of hardcoding reservation policies inside every repository or manually updating YAML files across teams, this architecture enables:

* **Centralized Control**: Platform Teams maintain all reservation mappings in a single, dedicated internal package.
* **Auto-Updates**: Consumer dbt projects point to the main branch of the internal platform package (`revision: main`), so new reservation assignments take effect immediately across all projects without requiring manual dependency upgrades.
* **Performance & Scale**: Configuration lookups pass the `project_name` parameter to load **only** the model mappings for the active project, eliminating org-wide dictionary parse overhead.
* **Zero Forking**: Consumer projects depend directly on official `masthead-data/bq_reservations` releases.
* **Graceful Fallbacks**: If a project or model is not listed in the central package, the system automatically falls back to local project `dbt_project.yml` variables.

---

## 3-Tier Architecture

```
Layer 1: bq_reservations (Official Package)
   └── Logic Engine: Normalizes IDs, matches models, and handles fallback logic.

Layer 2: acme_platform_config (Internal Platform Package)
   └── Central Storage: Maintains project-scoped reservation dictionaries (Data Only).

Layer 3: Customer dbt Projects (Consumer Projects)
   └── Execution: Imports Layer 1 & 2 and configures dbt Macro Dispatch.
```

---

## Step-by-Step Implementation

### Step 1: Create the Internal Platform Package (Layer 2)

The Platform Team creates a private repository (e.g., `acme_platform_config`) containing a single configuration macro named `default__get_bigquery_reservation_config`.

#### 1. Package Structure
```
acme_platform_config/
├── dbt_project.yml
└── macros/
    └── get_reservation_config.sql
```

#### 2. `dbt_project.yml`
```yaml
name: 'acme_platform_config'
version: '1.0.0'
config-version: 2
```

#### 3. Configuration Macro (`macros/get_reservation_config.sql`)
Define reservation policies grouped by `project_name` using standard dbt `unique_id` notation (`model.<project_name>.<model_name>`):

```jinja2
{% macro default__get_bigquery_reservation_config(project_name=none) %}
    {%- set all_configs = {
        'marketing_analytics': [
            {
                'reservation': 'projects/acme-prod/locations/us/reservations/marketing-capacity',
                'models': [
                    'model.marketing_analytics.stg_campaigns',
                    'model.marketing_analytics.fct_conversions'
                ]
            },
            {
                'reservation': 'none',
                'models': [
                    'model.marketing_analytics.adhoc_exploratory'
                ]
            }
        ],
        'finance_reporting': [
            {
                'reservation': 'projects/acme-prod/locations/us/reservations/finance-capacity',
                'models': [
                    'model.finance_reporting.fct_general_ledger'
                ]
            }
        ]
    } -%}

    {%- if project_name -%}
        {{ return(all_configs.get(project_name) or []) }}
    {%- else -%}
        {{ return(all_configs) }}
    {%- endif -%}
{% endmacro %}
```

---

### Step 2: Configure Consumer dbt Projects (Layer 3)

Data Teams install both packages and enable Macro Dispatch in their downstream repositories.

#### 1. Add Dependencies to `packages.yml`
To ensure platform rules update automatically on every `dbt deps` run without version capping, target the `main` branch for the platform config package:

```yaml
packages:
  - git: "git@github.com:acme-corp/acme-platform-config.git"
    revision: main  # Points to main branch so platform rule updates apply automatically
  - package: masthead-data/bq_reservations
    version: ">=0.2.0" # Uncapped version constraint to get latest package updates
```

Then run:
```bash
dbt deps
```

#### 2. Configure Macro Dispatch in `dbt_project.yml`
Route `bq_reservations` macro lookups to check `acme_platform_config` first:

```yaml
dispatch:
  - macro_namespace: bq_reservations
    search_order: ['acme_platform_config', 'bq_reservations']
```

---

### Step 3: Apply Reservations in Models

Because macros rely on model compilation context (`model.unique_id`), macro calls are invoked within model files (or via global/folder-level model config defaults).

#### Option A: Native Reservation Config (dbt v2+)
Set the `reservation` configuration property inside model config blocks:

```sql
-- models/fct_conversions.sql
{{
  config(
    materialized='table',
    reservation=bq_reservations.get_name_from_config()
  )
}}

SELECT * FROM {{ ref('stg_campaigns') }}
```

#### Option B: SQL Header Placement (dbt v1)
For older dbt-core versions, inject `SET @@reservation` via `sql_header`:

```sql
-- models/fct_conversions.sql
{{
  config(
    materialized='table',
    sql_header=bq_reservations.assign_from_config()
  )
}}

SELECT * FROM {{ ref('stg_campaigns') }}
```

---

## Fallback & Precedence Rules

When a model compiles, reservation resolution follows a strict priority chain:

1. **Central Platform Config (Layer 2)**: Checks `acme_platform_config` for an explicit match on `model.unique_id` or `model_name`.
2. **Local Project Variables (Layer 3)**: If no match is found in Layer 2, the system checks `vars: RESERVATION_CONFIG` in the project's own `dbt_project.yml`.
3. **Default Reservation**: If no rule matches anywhere, no `SET @@reservation` is emitted and BigQuery executes the query using the project's default assignment.
