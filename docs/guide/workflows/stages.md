# Workflow Stages

Workflow stages define the execution order and parallelism of jobs in an OFX workflow. Each stage consists of one or more jobs that can run in parallel, followed by dependent stages.

---

## How Stages Are Determined
- Jobs without `needs:` run in the first stage (in parallel)
- Jobs with `needs:` run after their dependencies complete
- Each new set of jobs with satisfied dependencies forms a new stage

---

## Example: Sequential and Parallel Stages
```yaml
name: Multi-Stage Attack
jobs:
  recon:
    name: Reconnaissance
    steps:
      - name: Scan target
        run: nmap ${{ inputs.target }}
  exploit:
    name: Exploitation
    needs: recon
    steps:
      - name: Run exploit
        run: python exploit.py
  loot:
    name: Data Exfiltration
    needs: exploit
    steps:
      - name: Collect data
        run: ./loot.sh
  notify:
    name: Notification
    needs: recon
    steps:
      - name: Send alert
        run: ./notify.sh
```

**Stages:**
1. `recon` (stage 1)
2. `exploit` and `notify` (stage 2, run in parallel)
3. `loot` (stage 3)

---

## Visualizing Stages
Use `ofx flow run <workflow.yml> --debug` to see stage breakdowns and job execution order.

---

## Best Practices
- Use `needs:` to control dependencies and avoid race conditions
- Only one interactive job per stage (see [Interactive Mode](../interactive-mode/index.md))
- Group independent jobs for faster execution

---

## See Also
- [Workflow Examples](examples.md)
- [Dependencies](dependencies.md)