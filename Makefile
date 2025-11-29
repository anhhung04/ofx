.PHONY: help install dev test clean build-nukita docker-nukita docker-build export-binary

help:
	@echo "OFX Makefile Commands:"
	@echo "  make install       - Install dependencies with uv"
	@echo "  make dev           - Install with dev dependencies"
	@echo "  make test          - Run tests"
	@echo "  make clean         - Remove build artifacts"
	@echo "  make build-nukita  - Compile Python files with Nukita"
	@echo "  make docker-nukita - Build Docker image with Nukita"
	@echo "  make docker-build  - Build standard Docker image"
	@echo "  make export-binary - Export compiled binary from Docker"

install:
	uv sync --no-dev

dev:
	uv sync

test:
	uv run pytest

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.codon" -delete

build-nukita:
	@echo "Building with Nukita..."
	@command -v nukita >/dev/null 2>&1 || { echo "Error: Nukita not found"; exit 1; }
	@nukita --version
	@mkdir -p build/nukita
	@nukita build --release --output build/nukita/ofx src/ofx/__init__.py
	@echo "Build complete: build/nukita/"

export-binary:
	@echo "Exporting binary from Docker build with Nukita..."
	@mkdir -p dist
	docker build -f Dockerfile.build --target=export --output type=local,dest=./dist .
	@echo "Binary exported to: dist/ofx"
