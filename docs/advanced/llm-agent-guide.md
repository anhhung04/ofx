# OFX Prompt Guide

Use this guide to write better prompts for LLMs when generating, fixing, or reviewing OFX workflows.

The goal is simple: produce valid workflows quickly, with fewer back-and-forth corrections.

---

## What to Include in Every Prompt

Give the model enough context to produce a runnable workflow on the first try.

- Objective: what the workflow should accomplish.
- Inputs: required user/runtime inputs.
- Secrets: required secret names.
- Execution model: local, cloud, matrix, or fleet.
- Constraints: tooling, OPSEC limits, timeout expectations.
- Output expectations: files and summary location.

If you skip these, most failures come from schema mismatch or ambiguous behavior.

---

## OFX Schema Rules (Must-Follow)

### Root and config keys

- Use `name` at root.
- Put user parameters under `dispatch.inputs`.
- Put secret definitions under `call.secrets`.
- Use `env` (not `envs`).

```yaml
dispatch:
  inputs:
    target:
      type: string
      required: true

call:
  secrets:
    API_KEY:
      required: true
```

### Jobs and dependencies

- Jobs live under `jobs`.
- Dependencies use `needs: [job_id]`.
- Independent jobs run in parallel by default.

### Steps

Each step must define **exactly one** execution type:

- `run`
- `script`
- `script_file`
- `uses`
- `task`

### Matrix and fleet

- Use `strategy.matrix` for combinational variations.
- Use `strategy.fleet` for target distribution across instances.
- Optional controls: `max_parallel`, `fail_fast`, `include`, `exclude`.

### Templates and context

Use Jinja expressions for runtime values:

- `{{ inputs.<name> }}`
- `{{ secrets.<name> }}`
- `{{ matrix.<key> }}`
- `{{ ctx.output_path }}`

Always write artifacts under `{{ ctx.output_path }}`.

---

## Prompt Template You Can Reuse

Copy this and fill in the placeholders.

```text
Generate a valid OFX workflow YAML.

Goal:
- <what should happen end-to-end>

Inputs:
- <name>: <type>, required=<true/false>, description=<...>

Secrets:
- <SECRET_NAME>: required=<true/false>

Execution:
- Run mode: <local|cloud>
- If cloud: provider/profile=<...>
- If matrix: keys=<...>, max_parallel=<...>
- If fleet: input=<...>, distribution=<chunk|round-robin|subnet|line>

Constraints:
- Use only: <tools/APIs>
- OPSEC requirements: <...>
- Retry/timeout behavior: <...>

Output:
- Save all artifacts under {{ ctx.output_path }}
- Include a final summary step

Return:
- YAML only
- Include brief comments only where needed
```

---

## Good Prompt Examples

### 1) Generate a new workflow

```text
Create an OFX workflow for web recon on a single target.
Inputs: target (string, required), ports (string, optional default "80,443").
Secrets: FOFA_KEY optional.
Use two jobs: recon and summarize. summarize depends on recon.
In recon, run nmap and httpx, store outputs in {{ ctx.output_path }}.
In summarize, generate a short report file.
Use env (not envs). Return YAML only.
```

### 2) Refactor an invalid workflow

```text
Fix this OFX workflow to conform to schema:
- move root inputs to dispatch.inputs
- move root secrets to call.secrets
- convert envs to env
- ensure each step has exactly one of run/script/script_file/uses/task
Preserve behavior and return corrected YAML only.
```

### 3) Add matrix/fleet behavior

```text
Update this workflow to use strategy.matrix for ports [80,443,8080]
and fleet distribution with chunk mode across 3 instances.
Keep existing job dependencies unchanged and preserve outputs.
Return only updated YAML.
```

---

## Common Prompting Mistakes

- Asking for OFX YAML without providing inputs/secrets schema.
- Requesting outputs in hardcoded paths instead of `{{ ctx.output_path }}`.
- Mixing multiple step run types in one step.
- Asking for cloud behavior without provider/profile details.
- Asking for "best effort" output while also requiring strict validation.

---

## Fast Validation Loop

After generation:

1. Run `ofx flow validate <workflow.yml>`.
2. If invalid, ask model to fix only schema issues.
3. Then ask model to improve behavior (performance/readability) in a second pass.

This two-pass approach reduces noisy rewrites.

---

## Recommended Prompting Workflow

1. Ask for a minimal valid workflow first.
2. Add matrix/cloud/fleet in a second request.
3. Add polish (comments, naming, summaries) last.

Small, incremental prompts are more reliable than one giant request.
