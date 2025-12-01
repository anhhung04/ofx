.PHONY: help install dev test clean build-nukita docker-nukita docker-build dist

help:
	@echo "OFX Makefile Commands:"
	@echo "  make install       - Install dependencies with uv"
	@echo "  make dev           - Install with dev dependencies"
	@echo "  make test          - Run tests"
	@echo "  make clean         - Remove build artifacts"
	@echo "  make build-nukita  - Compile Python files with Nukita"
	@echo "  make docker-nukita - Build Docker image with Nukita"
	@echo "  make docker-build  - Build standard Docker image"
	@echo "  make dist - Export compiled binary from Docker"

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

dist:
	@echo "Exporting distribution from Docker build..."
	@mkdir -p dist
	docker build -f Dockerfile.build --target=export --output type=local,dest=./dist .
	@echo "Distribution exported to: dist/"
