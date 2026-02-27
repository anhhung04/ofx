# LLM Agent Guide for OFX

This guide is intended for Large Language Models (LLMs) and AI code assistants to help them correctly write, structure, and debug OFX (Offensive Flow Executor) workflows. Use these instructions to avoid common schema mistakes when generating OFX `.yml` files.

---

## 1. Core Workflow Schema Rules

When generating an OFX workflow, adhere strictly to the following YAML schema structure:

- **Root Properties:** 
  - `name`: String, required.
  - `description`: String, optional.
  - `tags`: List of strings, optional.
- **Inputs:** Must be nested under `dispatch.inputs`. DO NOT put `inputs` at the root of the workflow.
  ```yaml
  dispatch:
    inputs:
      target:
        type: string
        required: true
        description: "Target domain"
  ```
- **Secrets:** Must be nested under `call.secrets`. DO NOT put `secrets` at the root.
  ```yaml
  call:
    secrets:
      API_KEY:
        type: string
        required: true
  ```
- **Environment Variables:** Use `env:` (dictionary), not `envs:`.

## 2. Jobs and Steps

- **Dependencies:** Use `needs: [job_name]` to define job dependencies. By default, jobs run in parallel unless `needs` are specified.
- **Strategy Matrix:**
  Use `strategy.matrix` to run variations of a job. Additional strategy options include `max_parallel` (int), `fail_fast` (bool), `include` (add combinations), and `exclude` (remove combinations).
- **Steps:** 
  - Each step must have **exactly one** action: 
    - `run:` (shell command)
    - `script:` (inline Python)
    - `script_file:` (path to a `.py` file)
    - `uses:` (URL to a reusable workflow)
  - You can use `continue_on_error: true` to prevent step failures from halting the workflow.
  - Environment variables inside steps are `env:`, not `envs:`.

## 3. Context & Templating (Jinja2)

OFX uses Jinja2 for templating. All template expressions are evaluated at runtime.

- **Variables:**
  - `{{ inputs.my_input }}`: Access a dispatched input.
  - `{{ secrets.my_secret }}`: Access a masked secret.
  - `{{ ctx.output_path }}`: The assigned output directory for the run. Do not hardcode `/tmp` or local paths; always write artifacts to `{{ ctx.output_path }}`.
  - `{{ ctx.run_id }}`: Unique string for the current execution run.

## 4. Python Scripts & Inter-Job Communication

OFX allows execution of Python directly via `script:` or `script_file:`.

- **Context Injections:** Scripts automatically receive `__ctx__`, `__workflow__`, `__job__`, and `__step__` globals.
- **Built-in APIs:** Scripts can import anything from `ofx.api.*` (e.g., `ofx.api.search`, `ofx.api.network`, `ofx.api.file`, `ofx.api.http`).
- **Channel Operations:** Used for asynchronous data passing between jobs.
  - `publish('channel_name', data_dict)`
  - `wait_for('channel_name', lambda d: condition)`
  - `subscribe('channel_name')` (generator)

## 5. Typical Perfect Workflow Example

```yaml
name: Example LLM Workflow
description: Demonstrates proper OFX schema for LLMs
tags: [example, demo]

dispatch:
  inputs:
    target:
      type: string
      required: true
      description: Target host

call:
  secrets:
    FOFA_KEY:
      required: false

env:
  GLOBAL_DEBUG: "true"

jobs:
  recon:
    name: Perform Recon
    strategy:
      matrix:
        ports: ["80", "443"]
      max_parallel: 2
    steps:
      - name: Scan Target
        run: nmap -p {{ matrix.ports }} {{ inputs.target }} > {{ ctx.output_path }}/nmap_{{ matrix.ports }}.txt
      
      - name: Signal Completion
        script: |
          publish('recon_status', {'port': '{{ matrix.ports }}', 'status': 'done'})

  analyze:
    name: Analyze Results
    needs: [recon]
    steps:
      - name: Process Output
        script_file: scripts/analyze.py

      - name: Summary
        run: echo "Analysis complete for {{ inputs.target }}"
```

By strictly following these schema parameters—especially wrapping inputs/secrets correctly and using `env:`, not `envs:`—you will successfully generate valid OFX workflows.
