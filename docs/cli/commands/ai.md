# AI Assistant Commands

> Generate workflows, analyze output, and chat interactively — powered by LLM providers.

---

## Usage

```bash
ofx ai <subcommand> [options]
```

---

## Overview

The `ai` command group integrates LLM providers into OFX for workflow generation, run output analysis, and interactive assistance. All commands support model override via `--model`.

---

## Subcommands

### generate

Generate an OFX workflow YAML from a natural language description.

```bash
ofx ai generate "<prompt>" [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Save generated YAML to a file path |
| `--model` | `-m` | Override LLM model (e.g. `claude-opus-4-6`) |

```bash
# Generate and print to stdout
ofx ai generate "scan a /24 network for open web ports and screenshot all HTTP services"

# Save to file
ofx ai generate "enumerate subdomains for a target domain" -o recon.yml
```

---

### analyze

Analyze workflow execution output with AI. Supports optional skill personas to focus the analysis on a specific red team phase.

```bash
ofx ai analyze [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--output-file` | `-f` | Workflow run output JSON file (or pipe via stdin) |
| `--workflow-file` | `-w` | Workflow YAML for additional context |
| `--skill` | `-s` | Analysis persona to apply (see table below) |
| `--model` | `-m` | Override LLM model |

#### Built-in Skills

| Skill | Focus Area |
|-------|------------|
| `recon` | Reconnaissance findings and target mapping |
| `exploit` | Exploitation opportunities and attack paths |
| `search` | Search and enumeration results |
| `lateral` | Lateral movement options |
| `persistence` | Persistence mechanisms |
| `privesc` | Privilege escalation vectors |
| `report` | Executive/technical report generation |
| `opsec` | Operational security review |

```bash
# Analyze recon output
ofx ai analyze --output-file results/output.json --skill recon

# Analyze with workflow context
ofx ai analyze -f results/output.json -w scan.yml --skill exploit

# Pipe output via stdin
cat results/output.json | ofx ai analyze --skill report
```

---

### chat

Start an interactive AI chat session about OFX. Ask questions about workflow syntax, API modules, cloud configuration, and more.

```bash
ofx ai chat [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--prompt` | `-p` | Opening message (skips interactive input) |
| `--model` | `-m` | Override LLM model |

Type `exit` or `quit` to end the session.

```bash
# Start interactive chat
ofx ai chat

# Start with a specific question
ofx ai chat --prompt "How do I set up matrix jobs with fleet distribution?"
```

---

### skills

List all available AI skill personas for the `analyze` command.

```bash
ofx ai skills
```

---

### setup

Show AI configuration status and environment variable reference. Use this to verify your API keys and provider settings are configured correctly.

```bash
ofx ai setup
```

---

## Configuration

AI commands require an LLM provider API key. Run `ofx ai setup` to see which environment variables are expected and their current status.

!!! info "Provider Setup"
    Run `ofx ai setup` to check your configuration and see the required environment variables for each supported provider.

---

## Examples

### End-to-End Workflow

```bash
# 1. Generate a workflow
ofx ai generate "nmap scan top 1000 ports on a target" -o scan.yml

# 2. Run it
ofx flow run scan.yml --input target=10.0.0.1

# 3. Analyze results
ofx ai analyze -f ~/.ofx/tmp/latest/output.json --skill recon

# 4. Get exploitation guidance
ofx ai analyze -f ~/.ofx/tmp/latest/output.json --skill exploit
```

### Interactive Help

```bash
# Ask the AI about OFX features
ofx ai chat --prompt "What template helpers are available for cloud jobs?"
```

---

## See Also

- [**Run Command**](run.md) — Execute workflows
- [**Templates Guide**](../../guide/templates.md) — Jinja2 templating reference
- [**Workflow Syntax**](../../guide/workflows.md) — Complete workflow reference
