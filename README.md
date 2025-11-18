
# Masthead Data package for BigQuery reservations assignments in dbt

## Overview

This package is designed to optimize BigQuery resource usage by automatically assigning compute reservations to dbt models based on predefined configuration. This system enables businesses to efficiently manage their BigQuery costs and resource allocation with minimal manual intervention.

## Key Benefits

- **Cost optimization**: Automatically route high-priority workloads to reserved slots and low-priority workloads to on-demand pricing
- **Resource efficiency**: Ensure critical data pipelines get guaranteed compute resources while non-critical tasks use flexible pricing
- **Automated re-assignment**: Once configured, reservations are applied automatically based on model categorization
- **Flexible configuration**: Easy adjustment of reservation policies through configuration updates

## Getting Started

### Initial Setup

Add the dependency to your `packages.yml`:

```yaml
packages:
  - git: "https://github.com/masthead-data/dbt-reservations.git"
    revision: "0.0.2"  # or latest version
```

Then run:

```bash
dbt deps
```

### Configuration Structure

Add the configuration to your `dbt_project.yml` defining reservation policies:

```yaml
# dbt_project.yml or profiles.yml
vars:
  RESERVATION_CONFIG:
    - tag: 'high_slots'
      reservation: 'projects/{project}/locations/{location}/reservations/{name}'
      models:
        - 'model.my_project.critical_dashboard'
        - 'model.my_project.revenue_report'

    - tag: 'low_slots'
      reservation: null  # Use default reservation
      models: []

    - tag: 'on_demand'
      reservation: 'none'  # Use on-demand pricing
      models:
        - 'model.my_project.ad_hoc_analysis'
```

**Configuration arguments:**

- `tag`: Human-readable identifier for the reservation category
- `reservation`: BigQuery reservation resource name:
  - Full path: `'projects/{project}/locations/{location}/reservations/{name}'`
  - `'none'`: for on-demand pricing
  - `null`: Use a default reservation
- `models`: Array of dbt model unique IDs that to be re-assigned

## Usage Examples

### Models

Add the reservation assignment to your model's config block:

```sql
-- models/my_critical_model.sql
{{
  config(
    materialized='table',
    sql_header=bq_reservations.assign_from_config()
  )
}}

SELECT
  customer_id,
  SUM(revenue) as total_revenue
FROM {{ ref('orders') }}
GROUP BY 1
```

**Example implementation** can be found in the [`integration_tests/`](./integration_tests) directory.

## Under the Hood

### How It Works

The package uses dbt's `sql_header` configuration option to inject BigQuery `SET` statements before the main statement execution. This ensures that reservation settings are applied in the same BigQuery job as the model creation.

### Supported Models

The package supports all dbt model types and contexts:

- **Models**: Uses `model.unique_id` to get the model identifier
- **Fallback**: Uses `this.identifier` if `model.unique_id` is not available

### Reservation Lookup

Models are matched against the `RESERVATION_CONFIG` using exact string, first-match semantics. If no match is found - no reservation override is applied.

### SQL Generation

Based on the matched reservation, the system generates appropriate SQL:

- **Defined Reservation ID**: `SET @@reservation='projects/{project}/locations/{location}/reservations/{name}';`
- **'none'**: `SET @@reservation='none';`, assigning to on-demand capacity
- **null/No match**: Empty string. No reservation re-assignment, BigQuery uses default.

### Finding Model Identifiers

List unique IDs of your models:

```bash
dbt ls --resource-type model
```

**Note**: The format in the configuration is: `model.<project_name>.<model_name>`.

## CLI Variable Override

You can override the configuration via CLI for testing or one-off runs:

```bash
dbt run --vars '{"RESERVATION_CONFIG": [{"tag": "high", "reservation": "projects/my-proj/locations/us/reservations/high", "models": ["model_my_project_my_model"]}]}'
```

## Troubleshooting

### Verifying Reservation Assignment

To check if your reservation is being applied correctly:

- Go to BigQuery Console → Query History
- Find your dbt run's query
- Check the "Reservation Name" field in the job details

### Common Issues

**Issue**: Macro not found error, e.g. `'bq_reservations' is undefined`

**Solution**: Ensure you've run `dbt deps` and the package is properly installed.

**Issue**: Reservation not being applied

**Solution**:

- Verify your model's unique ID is correctly listed in `RESERVATION_CONFIG`
- Run `dbt ls` to see all model unique IDs
- Check that `sql_header` is in the `{{ config() }}` block

**Issue**: Syntax error in BigQuery

**Solution**: Ensure the macro call in `sql_header` doesn't have quotes.
