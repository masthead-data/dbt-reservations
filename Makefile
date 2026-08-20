.DEFAULT_GOAL:=help

.PHONY: help
help:
	@echo "Available commands:"
	@echo "  make setup              - Create virtual environment and install nox + dev tools"
	@echo "  make test               - Run unit tests across all dbt versions (matrix)"
	@echo "  make integration-test   - Run integration tests across all dbt versions (requires GCP credentials)"
	@echo "  make clean              - Remove virtual environment and cache files"
	@echo "  make bump-version       - Bump version and commit (requires VERSION=x.x.x)"
	@echo "  make tag-release        - Tag and push release (requires VERSION=x.x.x)"
	@echo "  make release            - Run tests, bump version, and create release (requires VERSION=x.x.x)"

.PHONY: setup
setup:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r dev-requirements.txt
	@echo "Setup complete! Run 'source .venv/bin/activate' to enter the environment."

.PHONY: test
test:
	.venv/bin/nox

.PHONY: integration-test
integration-test:
	.venv/bin/nox -s integration-dbt-core-latest integration-dbt-core-v2-fixed

.PHONY: test-run
test-run:
	. .venv/bin/activate && cd integration_tests && \
	dbt --version && \
	dbt --warn-error deps && \
	dbt --warn-error build

.PHONY: clean
clean:
	rm -rf .venv/ .nox/ .pytest_cache/ logs/
	rm -rf integration_tests/target/ integration_tests/.target-*/ integration_tests/dbt_packages/ integration_tests/dbt_internal_packages/ integration_tests/logs/ integration_tests/.user.yml
	find . -type d -name __pycache__ -exec rm -rf {} +

.PHONY: bump-version
# make bump-version VERSION=x.x.x
bump-version:
	@if [ -z "$(VERSION)" ]; then echo "Error: VERSION is required. Use: make bump-version VERSION=x.x.x"; exit 1; fi
	@if [ -f .venv/bin/python ]; then .venv/bin/python scripts/bump_version.py $(VERSION); else python3 scripts/bump_version.py $(VERSION); fi
	@echo "Version bumped to $(VERSION)"

.PHONY: tag-release
# make tag-release VERSION=x.x.x
tag-release:
	@if [ -z "$(VERSION)" ]; then echo "Error: VERSION is required. Use: make tag-release VERSION=x.x.x"; exit 1; fi
	@git tag -a v$(VERSION) -m "Version $(VERSION)"
	@git push origin main --tags
	@echo "Tagged and pushed v$(VERSION)"

.PHONY: release
# make release VERSION=x.x.x
release: test bump-version tag-release
	@echo "Release v$(VERSION) complete!"
