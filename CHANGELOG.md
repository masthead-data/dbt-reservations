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

## [0.0.2] - 2024-11-25

### Added

- Dependabot auto-merge workflow for CI pipeline
- dbt Hub badge to README for better package visibility

### Changed

- Updated README package reference consistency and reservation configuration tags
- Modified `bump_version.py` script to use version tags without 'v' prefix
- Updated GitHub Actions dependencies: `actions/checkout` (4→5), `actions/setup-python` (4→6), `softprops/action-gh-release` (1→2)

### Fixed

- Fixed `bump_version.py` to handle missing `package_manifest.json` file gracefully

## [v0.0.2] - 2024-11-18

### Added

- Comprehensive unit tests for reservation macro (10 test cases covering edge cases)

### Changed

- Macro code doesn't change SQL if no matching reservation is found

## [v0.0.1] - 2024-11-15

### Added

- Initial release of `dbt-reservations` package
- Macro to assign BigQuery reservations to models based on configuration
- Integration tests for default and on-demand reservation assignments

[Unreleased]: https://github.com/masthead-data/dbt-reservations/compare/0.0.2...HEAD
[0.0.2]: https://github.com/masthead-data/dbt-reservations/compare/v0.0.2...0.0.2
[v0.0.2]: https://github.com/masthead-data/dbt-reservations/compare/v0.0.1...v0.0.2
[v0.0.1]: https://github.com/masthead-data/dbt-reservations/tag/v0.0.1
