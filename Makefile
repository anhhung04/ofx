.PHONY: help install dev test clean dist docs docs-clean

help:
	@echo "OFX Makefile Commands:"
	@echo "  make install       - Install dependencies with uv"
	@echo "  make dev           - Install with dev dependencies"
	@echo "  make test          - Run tests"
	@echo "  make clean         - Remove build artifacts"
	@echo "  make dist          - Export compiled package from Docker"
	@echo "  make docs          - Build documentation"
	@echo "  make docs-clean    - Remove built documentation"

install:
	uv sync --no-dev

dev:
	uv sync

test:
	uv run pytest

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov/ src/ofx/data/site/
	find ./src -type d -name __pycache__ -exec rm -rf {} +
	find ./src -type f -name "*.pyc" -delete
	find ./src -type f -name "*.pyo" -delete
	find ./src -type f -name "*.c" -delete
	find ./src -type f -name "*.so" -delete

dist:
	@echo "Exporting distribution from Docker build..."
	@mkdir -p dist
	docker build -f Dockerfile.build --target=export --output type=local,dest=./dist .
	@echo "Distribution exported to: dist/"

docs:
	@echo "Building documentation..."
	uv run --extra docs mkdocs build -f mkdocs.yml -d src/ofx/data/site
	@echo "Documentation built successfully in: src/ofx/data/site/"
	@echo "To serve locally, run: uv run ofx docs serve"

docs-clean:
	@echo "Cleaning documentation build..."
	rm -rf src/ofx/data/site/
	@echo "Documentation build removed"
