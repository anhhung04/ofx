# Workflow Dependencies

Dependencies control the execution order of jobs in an OFX workflow. Use the `needs:` field to specify which jobs must complete before a job can start.

---

## Syntax
```yaml
name: Build Pipeline
jobs:
  build:
    name: Build Application
    steps:
      - name: Compile code
        run: make
  test:
    name: Run Tests
    needs: build
    steps:
      - name: Execute tests
        run: pytest
  deploy:
    name: Deploy Application
    needs: [test]
    steps:
      - name: Deploy to production
        run: ./deploy.sh
```

---

## How It Works
- Jobs without `needs:` run in the first stage
- Jobs with `needs:` wait for their dependencies
- You can specify a single job or a list of jobs

---

## Example: Multiple Dependencies
```yaml
name: Complex Attack Chain
jobs:
  setup:
    name: Environment Setup
    steps:
      - name: Initialize environment
        run: ./setup.sh
  scan:
    name: Port Scan
    needs: setup
    steps:
      - name: Scan target
        run: nmap {{ inputs.target }}
  exploit:
    name: Exploitation
    needs: [setup, scan]
    steps:
      - name: Run exploit
        run: python exploit.py
```

---

## Best Practices
- Use dependencies to enforce correct order and avoid race conditions
- Avoid circular dependencies (will cause errors)
- Use dependencies to control parallelism and resource usage

---

## See Also
- [Workflow Stages](stages.md)
- [Workflow Examples](examples.md)