# Architecture

OFX is designed as a modular, extensible workflow engine for red teaming, automation, and DevSecOps. It separates workflow logic, job execution, API modules, and utilities for maximum flexibility.

---

## Core Components
- **Workflow Engine:** Parses YAML, resolves templates, manages execution
- **Job Runner:** Handles parallel and sequential job execution
- **Step Runner:** Executes commands, scripts, or code blocks
- **API Modules:** Provide reusable functions for recon, exploitation, post-exploitation
- **Hooks System:** Injects custom logic at workflow, job, or step level
- **Template Engine:** Uses Jinja2 for dynamic variables and logic

---

## Execution Flow
1. Load workflow YAML
2. Resolve templates with inputs/secrets
3. Execute jobs (respecting dependencies)
4. Run steps within each job
5. Trigger hooks at each lifecycle stage
6. Collect outputs and results

---

## Extending OFX
- Add new API modules in `src/ofx/api/`
- Add custom connectors for new data sources
- Use hooks and templates for advanced logic

---

## See Also
- [Quickstart Guide](../quickstart/index.md)
- [Workflow Syntax](../../guide/workflows/index.md)