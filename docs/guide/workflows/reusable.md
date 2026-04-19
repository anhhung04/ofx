# Reusable Workflows (`uses:`)

Reusable workflows let you compose complex pipelines from smaller, self-contained workflow files. A step with `uses:` runs another workflow as a nested execution within the current run context.

---

## Lookup Order

When you reference a workflow with `uses:`, OFX resolves it in this order:

1. **Relative or absolute file path** — `./shared/recon.yml` or `/opt/workflows/scan.yml`
2. **Workflow search paths** — `~/.ofx/workflows/` and installed collection directories
3. **HTTP/HTTPS URL** — `https://example.com/workflow.yml`
4. **Git repository URL** — `https://github.com/user/repo` (clones and loads the main workflow file)

---

## Passing Inputs

Use `with:` to pass inputs to the reusable workflow:

```yaml
jobs:
  sub:
    steps:
      - uses: ./shared/credential-check.yml
        with:
          target: "{{ inputs.target }}"
          ports: "80,443"
```

The reusable workflow declares expected inputs via its `call.inputs` section:

```yaml
# shared/credential-check.yml
name: credential-check
call:
  inputs:
    target:
      required: true
    ports:
      required: false
      default: "1-1000"
jobs:
  check:
    steps:
      - run: nmap -p {{ inputs.ports }} {{ inputs.target }}
```

---

## Passing Secrets

Pass specific secrets or inherit all parent secrets:

```yaml
# Pass specific secrets
- uses: ./scan.yml
  with:
    target: "{{ inputs.target }}"
  secrets:
    API_KEY: "{{ secrets.SHODAN_KEY }}"

# Inherit all parent secrets
- uses: ./scan.yml
  with:
    target: "{{ inputs.target }}"
  secrets: inherit
```

The reusable workflow declares expected secrets via `call.secrets`:

```yaml
call:
  secrets:
    API_KEY:
      required: false
```

---

## Consuming Outputs

Reusable workflows can expose outputs via `call.outputs`:

```yaml
# shared/recon.yml
name: recon
call:
  outputs:
    hosts: "{{ jobs.scan.outputs.live_hosts }}"
jobs:
  scan:
    outputs:
      live_hosts: "{{ steps['probe'].outputs.hosts }}"
    steps:
      - name: probe
        run: |
          echo "hosts=10.0.0.1,10.0.0.2" >> $OFX_OUTPUTS
```

The parent workflow accesses the output through the step:

```yaml
steps:
  - name: run-recon
    uses: ./shared/recon.yml
    with:
      target: "{{ inputs.target }}"

  - run: echo "Found hosts: {{ steps['run-recon'].outputs.hosts }}"
```

---

## Remote Workflows

Reference workflows from GitHub repositories:

```yaml
steps:
  - uses: https://github.com/user/recon-workflows
    with:
      target: "{{ inputs.target }}"
```

OFX clones the repository and loads its main workflow file. Remote workflows are cached under `~/.ofx/cache`.

---

## Best Practices

- Keep reusable workflows focused on a single responsibility
- Always declare `call.inputs` with `required` and `description` for clarity
- Use `secrets: inherit` sparingly — prefer explicit secret passing for security
- Use `call.outputs` to expose results to the caller

---

[← Back to Workflows Overview](../workflows.md)
