# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

## [v0.2.0] - 2026-08-19

### Added

- Added integration test models for nested directory path resolution (`slots_path`, `slots_path_incremental`).
- Added integration test cases for incremental models (`slots_incremental`), materialized views (`slots_materialized_view`), pre/post hooks with reservation isolation (`slots_hooks`), snapshots (`slots_snapshot`), and schema tests.

### Changed

- Refactored `assign_from_config` to delegate lookup, normalization, and matching entirely to `get_name_from_config` for DRY macro architecture.
- Enforced supported resource type filtering: restricted matching to `model`, `snapshot`, and `test` resources, explicitly excluding `seed` and `view` per specification.
- Raised minimum supported `dbt-core` version requirement to `>=1.12.0` (dropped support for deprecated `1.9`).

## [v0.1.1] - 2026-08-12

### Fixed

- Updated `get_name_from_config` macro to read `RESERVATION_CONFIG` variable instead of `RESERVATION_CONFIG_NATIVE` for consistency across engines.
- Cleaned up integration test matrix configuration and unit tests for unified variable naming.

## [v0.1.0] - 2026-07-08

### Added

- Native dbt-core v2 (Rust / dbt-fusion) reservation support via `reservation` config key
- Integration test matrix: dbt-core 1.9, latest, v2-preview, dbt-fusion (including fixed-binary variants)
- End-to-end BQ job reservation verification
- Added `get_name_from_config` macro to retrieve reservation name from model config for v2 engine

## [v0.0.3] - 2025-11-26

### Added

- Dependabot auto-merge workflow
- dbt Hub badge in README
- Package details in `package-lock.yml`

### Changed

- Refactored versioning workflow (eliminated duplicate logic between script and Makefile)
- Updated GitHub Actions: `actions/checkout` (4→6), `actions/setup-python` (4→6), `softprops/action-gh-release` (1→2)
- Improved README clarity and consistency

### Removed

- handling of `package_manifest.json` in `bump_version.py`

## [v0.0.2] - 2025-11-18

### Added

- Comprehensive unit tests for reservation macro (10 test cases covering edge cases)

### Changed

- Macro code doesn't change SQL if no matching reservation is found

## [v0.0.1] - 2025-11-15

### Added

- Initial release of `dbt-reservations` package
- Macro to assign BigQuery reservations to models based on configuration
- Integration tests for default and on-demand reservation assignments

[Unreleased]: https://github.com/masthead-data/dbt-reservations/compare/v0.2.0...HEAD
[v0.2.0]: https://github.com/masthead-data/dbt-reservations/compare/v0.1.1...v0.2.0
[v0.1.1]: https://github.com/masthead-data/dbt-reservations/compare/v0.1.0...v0.1.1
[v0.1.0]: https://github.com/masthead-data/dbt-reservations/compare/v0.0.3...v0.1.0
[v0.0.3]: https://github.com/masthead-data/dbt-reservations/compare/v0.0.2...v0.0.3
[v0.0.2]: https://github.com/masthead-data/dbt-reservations/compare/v0.0.1...v0.0.2
[v0.0.1]: https://github.com/masthead-data/dbt-reservations/tag/v0.0.1
