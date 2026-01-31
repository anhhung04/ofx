.PHONY: help install dev test clean dist docs coverage coverage-html coverage-report
.PHONY: deb deb-clean packages packages-multiarch pkg-windows pkg-clean version

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
	@echo "  make packages        - Build all packages (deb, rpm, wheel) via Docker"
	@echo "  make packages-multiarch - Build for amd64 and arm64"
	@echo "  make deb             - Build Debian package only"
	@echo "  make pkg-windows     - Build Windows executable"
	@echo "  make pkg-clean       - Clean all package build artifacts"
	@echo ""
	@echo "Version:"
	@echo "  make version V=x.y.z - Bump version (e.g., make version V=0.3.2)"

install:
	uv sync --no-dev

dev:
	uv sync

test:
	uv run --extra test pytest

coverage:
	uv run --extra test pytest --cov=src/ofx --cov-report=term-missing

coverage-html:
	uv run --extra test pytest --cov=src/ofx --cov-report=html --cov-report=term-missing
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

dist:
	@echo "Exporting distribution from Docker build..."
	@mkdir -p dist
	docker build -f Dockerfile.fpm --target=export --output type=local,dest=./dist .
	@echo "Distribution exported to: dist/"

docs:
	@echo "Building documentation..."
	uv run --extra docs mkdocs build --clean --strict -f mkdocs.yml -d site
	@echo "Documentation built successfully in: src/ofx/data/site/"
	@echo "To serve locally, run: uv run ofx docs serve"

# =============================================================================
# Package Building (Docker-based)
# =============================================================================

# Build all packages for current architecture
packages:
	@echo "Building all packages (deb, rpm, wheel)..."
	@chmod +x scripts/build-packages.sh
	bash scripts/build-packages.sh

# Build for AMD64 and ARM64
packages-multiarch:
	@echo "Building packages for amd64 and arm64..."
	@chmod +x scripts/build-packages.sh
	bash scripts/build-packages.sh --multiarch

# Build Debian package only (native, not Docker)
deb:
	@echo "Building Debian package..."
	@chmod +x scripts/build-deb.sh
	bash scripts/build-deb.sh

# Build Windows executable (run on Windows only)
pkg-windows:
	@echo "Building Windows executable..."
	pip install pyinstaller
	python packaging/windows/build-exe.py
	@echo "Windows executable built in dist/"

# Clean all package artifacts
pkg-clean:
	@echo "Cleaning package build artifacts..."
	rm -rf dist/packages dist/*.deb dist/*.rpm dist/*.exe dist/*.whl
	rm -rf packaging/debian/.debhelper packaging/debian/ofx packaging/debian/files
	rm -f packaging/debian/*.debhelper* packaging/debian/*.substvars
	rm -f ../ofx_*.deb ../ofx_*.changes ../ofx_*.buildinfo 2>/dev/null || true
	@echo "Package build artifacts cleaned."

deb-clean: pkg-clean

# =============================================================================
# Version Management
# =============================================================================

# Bump version: make version V=0.3.2
version:
ifndef V
	$(error Usage: make version V=x.y.z)
endif
	@chmod +x scripts/bump-version.sh
	bash scripts/bump-version.sh $(V)