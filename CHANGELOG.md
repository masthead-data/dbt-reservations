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

## [v0.0.3] - 2024-11-26

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

[Unreleased]: https://github.com/masthead-data/dbt-reservations/compare/v0.0.3...HEAD
[v0.0.3]: https://github.com/masthead-data/dbt-reservations/compare/v0.0.2...v0.0.3
[v0.0.2]: https://github.com/masthead-data/dbt-reservations/compare/v0.0.1...v0.0.2
[v0.0.1]: https://github.com/masthead-data/dbt-reservations/tag/v0.0.1
