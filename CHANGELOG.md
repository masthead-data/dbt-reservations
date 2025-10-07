# Changelog

## [Unreleased]

### Added
- `bq_reservation_from_config()` macro for dynamic BigQuery reservation management
- Comprehensive unit tests for reservation macro (10 test cases covering all edge cases)
- Full README documentation with usage examples for both macros
- Support for `RESERVATION_CONFIG` variable to map models to BigQuery reservations
- Namespace-based scoping in reservation macro for reliable matching behavior

### Fixed
- Removed unsupported Jinja `break` tag, replaced with conditional assignment
- Fixed variable scoping issue in loop using `namespace()` to persist matched entry
- Added missing `add_model_id_comment.sql` macro file
- Fixed duplicate `[pytest]` section in `pytest.ini`

### Changed
- Updated macro to use first-match semantics for multiple matching entries
- Cleaned up debug comments from production macro code

### Testing
- Created `.venv` virtual environment for isolated testing
- All 12 unit tests passing (10 for reservation macro, 2 for model ID macro)
- Verified compilation in sample project produces correct SET statements

## Test Coverage

The `bq_reservation_from_config` macro now has comprehensive test coverage:

1. ✅ Basic reservation matching
2. ✅ Explicit "none" reservation handling
3. ✅ NULL reservation handling
4. ✅ No matching rule behavior
5. ✅ Empty models list handling
6. ✅ First-match wins for multiple matches
7. ✅ Fallback to `this.identifier`
8. ✅ Empty config handling
9. ✅ SET statement formatting validation
10. ✅ Custom prefix support

## Configuration Example

```yaml
# dbt_project.yml
vars:
  RESERVATION_CONFIG:
    - tag: high_priority
      reservation: "projects/my-project/locations/us/reservations/high-compute"
      models:
        - model.my_project.important_model
        - model.my_project.critical_dashboard

    - tag: on_demand
      reservation: "none"
      models:
        - model.my_project.ad_hoc_query
```

## Usage in Models

```sql
{{ dbt_reservation_setter.bq_reservation_from_config() }}

select * from my_source
```

## Verified Output

Sample compilation with config shows correct behavior:
- `hello.sql`: Emits `SET @@reservation= "projects/my-project/locations/us/reservations/high"`
- `customers.sql`: Emits `SET @@reservation= "projects/my-project/locations/us/reservations/high"`
- Unmatched models: Emit comment `-- bq_reservation_from_config: no matching reservation rule for <model_id>`
