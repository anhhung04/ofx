# Jobs

Jobs are the main building blocks of an OFX workflow. Each job contains one or more steps and can depend on other jobs. Jobs run in stages — either in parallel or sequentially based on dependencies.

---

## Job Structure

```yaml
jobs:
  recon:
    steps:
      - run: nmap {{ inputs.target }}
  exploit:
    needs: recon
    steps:
      - run: python exploit.py
```

---

## Job Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | `""` | Display name for the job |
| `steps` | list | — | **Required.** List of steps to execute (min 1) |
| `needs` | str/list | `[]` | Job dependencies — other jobs that must complete first |
| `if` | bool/str | `true` | Conditional execution (`success()`, `failure()`, `always()`, or Jinja2 expression) |
| `strategy` | object | `null` | Matrix strategy for running multiple job variations |
| `env` | dict | `{}` | Environment variables available to all steps in the job |
| `outputs` | dict | `{}` | Job outputs — template expressions promoting step outputs |
| `defaults` | object | `{}` | Default run config overrides (shell, working directory) |
| `cloud` | str/object | `null` | Cloud VPS configuration — profile name or inline `CloudConfig` |

---

## Parallel and Sequential Jobs

Jobs without `needs` run in parallel in the first stage. Jobs with `needs` wait for all dependencies:

```yaml
jobs:
  # Stage 1: scan_tcp and scan_udp run in parallel
  scan_tcp:
    steps:
      - run: nmap -sS {{ inputs.target }}

  scan_udp:
    steps:
      - run: nmap -sU {{ inputs.target }}

  # Stage 2: analyze waits for both scans
  analyze:
    needs: [scan_tcp, scan_udp]
    steps:
      - run: python analyze.py
```

---

## Conditional Execution

Control whether a job runs using `if`:

```yaml
jobs:
  scan:
    steps:
      - run: nmap {{ inputs.target }}

  notify:
    needs: [scan]
    if: failure()
    steps:
      - run: echo "Scan failed!" | notify

  cleanup:
    needs: [scan]
    if: always()
    steps:
      - run: ./cleanup.sh
```

| Condition | Runs when... |
|-----------|-------------|
| `success()` | All dependencies succeeded (default) |
| `failure()` | Any dependency failed |
| `always()` | Regardless of dependency outcomes |
| Jinja2 expression | Expression evaluates truthy |

---

## Job Outputs

Promote step outputs to the job level for consumption by dependent jobs:

```yaml
jobs:
  scan:
    outputs:
      open_ports: "{{ steps['port-scan'].outputs.open_ports }}"
    steps:
      - name: port-scan
        run: |
          echo "open_ports=22,80,443" >> $OFX_OUTPUTS

  exploit:
    needs: [scan]
    steps:
      - run: echo "Ports: {{ jobs.scan.outputs.open_ports }}"
```

---

## Cloud Jobs

Add a `cloud` field to run the job on a remote VPS:

```yaml
jobs:
  remote-scan:
    cloud: do-nyc              # Profile from ~/.ofx/cloud.yml
    steps:
      - task: nmap
        with:
          target: "10.0.0.0/24"
          ports: "1-65535"

  local-analysis:
    needs: [remote-scan]
    steps:
      - run: python analyze.py  # Runs locally
```

`cloud` accepts a profile name (string) or an inline config object. See [Cloud Runners](../cloud-runners.md).

---

## Best Practices

- Use clear, descriptive job IDs (`recon`, `exploit`, `cleanup` — not `job1`, `job2`)
- Group related steps in the same job
- Use `needs` to control execution order and maximize parallelism
- Use `if: always()` for cleanup/notification jobs
- Keep job outputs explicit — only promote what downstream jobs actually need

---

## See Also
- [Steps](steps.md)
- [Matrix Strategy](matrix-strategy.md)
- [Workflow Stages](../workflows/stages.md)
- [Cloud Runners](../cloud-runners.md)