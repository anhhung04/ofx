# Contributing to OFX

Thanks for your interest in contributing to OFX! This document outlines the process and guidelines for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Style Guide](#style-guide)
- [Testing](#testing)
- [Reporting Bugs](#reporting-bugs)
- [Feature Requests](#feature-requests)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ofx.git
   cd ofx
   ```
3. **Add upstream remote:**
   ```bash
   git remote add upstream https://github.com/anhhung04/ofx.git
   ```

## Development Setup

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --extra test

# Verify setup
uv run ofx --help
uv run pytest
```

## Making Changes

1. **Create a feature branch** from `master`:
   ```bash
   git checkout -b feat/my-feature
   ```

2. **Make your changes.** Keep changes focused and atomic.

3. **Run tests and linters:**
   ```bash
   uv run pytest
   uv run ruff check src/
   uv run ruff format src/
   uv run mypy src/
   ```

4. **Commit** using [conventional commits](https://www.conventionalcommits.org/)
   ```bash
   git commit -m "feat: add support for X"
   ```

### Commit Message Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Common prefixes:

| Prefix     | Description                         |
| ---------- | ----------------------------------- |
| `feat:`    | A new feature                       |
| `fix:`     | A bug fix                           |
| `docs:`    | Documentation changes               |
| `chore:`   | Maintenance, tooling, deps          |
| `refactor:`| Code restructuring without feature  |
| `test:`    | Adding or updating tests            |
| `ci:`      | CI/CD changes                       |

## Pull Request Process

1. Push your branch and create a PR against `master`.
2. Ensure the PR title follows conventional commits.
3. Link any related issues in the description.
4. CI will run tests and linters — resolve any failures.
5. A maintainer will review your PR. Please respond to feedback.
6. Once approved, your PR will be squashed and merged.

## Style Guide

- **Python 3.12+** with free-threaded build support
- **Ruff** for linting and formatting (line length: 88)
- **mypy** for type checking
- Follow existing patterns:
  - Async-first execution model
  - Propagate `RunContext` consistently
  - Use Pydantic v2 models with kebab-case aliases for YAML fields
  - Use `typing.Annotated` for Typer CLI options

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/ofx --cov-report=term-missing

# Run a single test file
uv run pytest tests/test_flowrun.py -v
```

New features should include tests. Bug fixes should include a regression test.

## Reporting Bugs

Use the [Bug Report](https://github.com/anhhung04/ofx/issues/new?template=bug_report.md) issue template. Include:

- OFX version (`ofx --version`)
- Python version (`python --version`)
- Operating system
- Steps to reproduce
- Expected vs actual behavior

## Feature Requests

Use the [Feature Request](https://github.com/anhhung04/ofx/issues/new?template=feature_request.md) issue template. Describe:

- The problem you're solving
- Your proposed solution
- Alternatives considered
