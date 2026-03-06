
# OFX: Offensive Flow Executor

> :rocket: **Advanced Red Team Automation Toolkit**

---

OFX is a modular workflow runner for offensive automation, supporting parallel jobs, templating, and built-in APIs for recon, exploitation, and post-exploitation.

| Feature                | Description                                                                 |
|------------------------|-----------------------------------------------------------------------------|
| **YAML Workflows**     | Compose complex attack chains with dependencies and parallel execution.      |
| **Built-in APIs**      | Recon, exploitation, post-exploitation modules ready for use.                |
| **Jinja Templates**    | Dynamic inputs, envs, secrets, and commands.                                 |
| **Async Engine**       | Fast, concurrent execution with rich progress output.                        |
| **Cloud Integration**  | Run jobs on DigitalOcean, AWS, or static VPS.                                |
| **Collections**        | Installable workflow packages for easy sharing and reuse.                    |

> [!TIP]
> See the [Getting Started](getting-started/quickstart.md) guide for your first workflow.

---

## Project Structure

- **src/ofx/**: Core engine, runners, models, APIs
- **docs/**: User documentation (split by topic)
- **tests/**: Unit and integration tests

---

## Quick Links

- [Quickstart](getting-started/quickstart.md)
- [Workflow Design](guide/workflows.md)
- [Cloud Execution](guide/cloud-runners.md)
- [API Reference](reference/api.md)
- [CLI Reference](cli/commands.md)

---

> [!IMPORTANT]
> OFX is async-first and modular. All runners, APIs, and cloud providers are extendable. See [Extending Data Modules](guide/extending-data-modules.md).
# Install with uv
uv tool install ofx

# Or with pip
pip install ofx

# Verify installation
ofx --version
```

## ⚡ Key Features

=== "Workflow Engine"

    ```yaml
    name: simple-scan
    jobs:
      nmap-scan:
        steps:
          - run: nmap -sV {{ inputs.target }}
            id: scan_result
    ```

    Define your operations as code. Share, version, and repeat your red team engagements with confidence.

=== "Python API"

    ```python
    from ofx.api.reconnaissance import ShodanClient

    shodan = ShodanClient()
    results = shodan.search("org:TargetCorp")
    for host in results:
        print(f"Found: {host.ip_str}")
    ```

    Leverage the power of Python to script advanced logic and integrations.

=== "Interactive Mode"

    ```bash
    ofx interactive
    ```

    Drop into a fully loaded shell with all your tools and context ready to go.

## 📚 Documentation

[**Getting Started**](getting-started/quickstart.md){ .md-button }
[**User Guide**](guide/workflows.md){ .md-button }
[**API Reference**](reference/api.md){ .md-button }
