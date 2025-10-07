.DEFAULT_GOAL:=help

.PHONY: help
help:
	@echo "Available commands:"
	@echo "  make setup         - Create virtual environment and install dependencies"
	@echo "  make test          - Run all tests"
	@echo "  make clean         - Remove virtual environment and cache files"
	@echo "  make bump-version  - Bump version and commit (requires VERSION=x.x.x)"
	@echo "  make tag-release   - Tag and push release (requires VERSION=x.x.x)"
	@echo "  make release       - Run tests, bump version, and create release (requires VERSION=x.x.x)"

.PHONY: setup
setup:
	python -m venv .venv
	. .venv/bin/activate && pip install -r dev-requirements.txt

.PHONY: test
test:
	. .venv/bin/activate && pytest -v

.PHONY: integration-test
integration-test:
	. .venv/bin/activate && cd integration_tests && \
	dbt --version && \
	dbt --warn-error deps && \
    dbt --warn-error run

.PHONY: clean
clean:
	rm -rf .venv
	rm -rf .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

.PHONY: bump-version
# make bump-version VERSION=0.1.1
bump-version:
	@if [ -z "$(VERSION)" ]; then echo "Error: VERSION is required. Use: make bump-version VERSION=0.1.1"; exit 1; fi
	@python scripts/bump_version.py $(VERSION)
	@echo "Version bumped to $(VERSION)"

.PHONY: tag-release
# make tag-release VERSION=0.1.1
tag-release:
	@if [ -z "$(VERSION)" ]; then echo "Error: VERSION is required. Use: make tag-release VERSION=0.1.1"; exit 1; fi
	@git tag -a v$(VERSION) -m "v$(VERSION)"
	@git push origin main --tags
	@echo "Tagged and pushed v$(VERSION)"

.PHONY: release
# make release VERSION=0.1.1
release: test bump-version tag-release
	@echo "Release v$(VERSION) complete!"
