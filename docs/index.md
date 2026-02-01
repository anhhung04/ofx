---
hide:
  - navigation
  - toc
---

<div class="hero-section">
  <h1>OFX</h1>
  <p>The Advanced Offensive Flow Executor for Red Teaming Operations</p>
  <div class="hero-actions">
    <a href="getting-started/quickstart/" class="hero-button primary">Get Started</a>
    <a href="reference/api/" class="hero-button secondary">API Reference</a>
  </div>
</div>

<div class="grid cards" markdown>

-   :material-rocket-launch: **Powerful Workflows**

    Build complex attack chains with YAML-based workflows. Support for async execution, dependencies, and matrix strategies.

-   :material-api: **Rich API Ecosystem**

    Extensive Python API for reconnaissance, exploitation, and post-exploitation. Integrate seamlessly with your custom tools.

-   :material-console: **CLI First**

    Robust CLI for managing projects, secrets, and assets. verifying workflows and running interactive sessions.
    
-   :material-puzzle: **Modular Design**

    Plugin-based architecture. Easily extend with new runners, connectors, and exploit modules.

</div>

## 🚀 Quick Start

Install OFX and get running in seconds:

```bash
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
