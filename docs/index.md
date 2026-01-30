# Welcome to OFX

> **OFX** — Build and run red-team workflows with async execution, reusable subflows, hooks, and tool installers.

---

## 🚀 Quick Start

```bash
# Install
uv sync                    # or: pip install .

# Verify installation
ofx --help
ofx doctor

# Serve docs locally
ofx docs serve
```

**Requirements:** Python 3.14+, Git

---

## ⚡ Essential Commands

| Command | Description |
|---------|-------------|
| `ofx flow validate <workflow>` | Validate workflow syntax |
| `ofx flow run <workflow>` | Execute a workflow |
| `ofx flow run <workflow> --input key=val` | Run with inputs |
| `ofx secret set NAME` | Add a secret |
| `ofx secret list` | List all secrets |
| `ofx x run <workflow>` | Shorthand alias |

---

## 📝 Your First Workflow

Create `hello.yml`:

```yaml
name: hello
jobs:
  greet:
    steps:
      - run: echo "Hello from OFX"
```

Run it:

```bash
ofx flow run hello
```

**Expected:** Progress spinner → `Hello from OFX`

---

## 📚 Documentation Guide

### Getting Started
- [**Quick Start**](getting-started/quickstart.md) — 5-minute tutorial
- [**Core Concepts**](getting-started/concepts.md) — Architecture overview

### Building Workflows
- [**Workflows**](guide/workflows.md) — Workflow structure and syntax
- [**Jobs & Steps**](guide/jobs-steps.md) — Parallel execution
- [**Templates**](guide/templates.md) — Jinja2 templating & helper functions

### Operations
- [**Secrets & Inputs**](guide/secrets-inputs.md) — Secure credential handling
- [**Interactive Mode**](guide/interactive-mode.md) — Real-time interaction

### Reference
- [**CLI Commands**](cli/commands.md) — Full command reference
- [**API Overview**](api/overview.md) — Python API documentation
