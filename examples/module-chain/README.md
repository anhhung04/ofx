# Module chain example

Demonstrates the OFX module system: builtin modules (`shell`, `python`) and a
custom user-defined function (UDF) module chained with retry and branching.

## Files

- `workflow.yml` — a 5-step exploit chain:
  1. `recon` — builtin `shell` module emits a fake port list.
  2. `parse` — builtin `python` module parses it and exports `open_ports`.
  3. `plan` — custom UDF module (`my_module.py::run`) builds an attack plan;
     retried twice on failure.
  4. `exploit-branch` — runs only on `success()`, consumes plan outputs.
  5. `fallback-branch` — runs only on `failure()` of the previous steps.
- `my_module.py` — example UDF module (`def run(ctx)` contract).

## Run

```bash
ofx flow run examples/module-chain/workflow.yml -o /tmp/ofx-module-chain
```

Expected: exit code 0; the run log shows output capture from all three module
kinds and the plan produced by the UDF.
