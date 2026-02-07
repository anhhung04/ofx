.PHONY: help install dev test clean docs coverage coverage-html coverage-report deb

help:
	@echo "OFX Makefile Commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install         - Install dependencies with uv"
	@echo "  make dev             - Install with dev dependencies"
	@echo "  make test            - Run tests"
	@echo "  make coverage        - Run tests with coverage report"
	@echo "  make coverage-html   - Run tests and generate HTML coverage report"
	@echo "  make clean           - Remove build artifacts"
	@echo "  make docs            - Build documentation"
	@echo ""
	@echo "Packaging:"
	@echo "  make deb             - Build Debian package via Docker"

install:
	uv sync --no-dev

dev:
	uv sync

test:
	UV_LINK_MODE=copy uv run --extra test pytest

coverage:
	UV_LINK_MODE=copy uv run --extra test pytest --cov=src/ofx --cov-report=term-missing

coverage-html:
	UV_LINK_MODE=copy uv run --extra test pytest --cov=src/ofx --cov-report=html --cov-report=term-missing
	@echo "Coverage report generated in: htmlcov/index.html"

coverage-report:
	@if [ -d "htmlcov" ]; then \
		python3 -m http.server 8080 --directory htmlcov & \
		echo "Coverage report available at: http://localhost:8080"; \
		echo "Press Ctrl+C to stop the server"; \
	else \
		echo "No coverage report found. Run 'make coverage-html' first."; \
	fi

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov/ src/ofx/data/site/
	find ./src -type d -name __pycache__ -exec rm -rf {} +
	find ./src -type f -name "*.pyc" -delete
	find ./src -type f -name "*.pyo" -delete
	find ./src -type f -name "*.c" -delete
	find ./src -type f -name "*.so" -delete


docs:
	@echo "Building documentation..."
	uv run --link-mode=copy --extra docs mkdocs build --clean --strict -f mkdocs.yml -d site
	@echo "Documentation built successfully in: src/ofx/data/site/"
	@echo "To serve locally, run: uv run ofx docs serve"

deb:
	@echo "Building Debian package via Docker..."
	@mkdir -p dist/packages
	docker build -f Dockerfile.deb --target=export --output type=local,dest=dist/packages .
	@echo "Debian package exported to: dist/packages/"
