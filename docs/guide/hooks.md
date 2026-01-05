# Hooks System

Step hooks only. Workflow/job hooks are not executed by the runner.

## Supported step hooks

| Hook | When |
| --- | --- |
| `before_step` | right before the step runs |
| `after_step` | always after completion |
| `on_retry` | before each retry (if `retry > 0`) |
| `on_timeout` | when the step hits its timeout |
| `on_skip` | when `run_if` is false before start |

Notes: hook shell/working directory follow the step; 1-minute timeout; failures are logged but do not stop the step; hooks cannot change outputs (use the main step body for that).

## Minimal example

```yaml
steps:
  - name: Scan
    run: nmap ${{ inputs.target }}
    retry: 1
    timeout: 2
    hooks:
      before_step: { script: echo "starting" }
      on_retry: { script: echo "retry" }
      on_timeout: { script: echo "timeout" }
      after_step: { script: echo "done" }
```

## Skip path

```yaml
- name: Maybe run
  run: ./task.sh
  run_if: ${{ inputs.enabled }}
  hooks:
    on_skip: { script: echo "skipped" }
```

## Quick reminders

- Keep hook logic short; heavy work belongs in the step.
- Hooks share env/working directory with the step.
- Prefer logging/notifications/cleanup; avoid mutating secrets or outputs.

See also: [jobs & steps](jobs-steps.md), [workflows](workflows.md), [templates](templates.md).
  on_start:
    script: echo "Workflow started at $(date)"
    language: shell
  
  on_success:
    script: python notify.py --status success
    language: shell

# Bad - Doing too much
hooks:
  on_start:
    script: |
      echo "Starting"
      python setup.py
      curl https://api.example.com
      # ... 50 more lines
    language: shell
```

### 2. Handle Errors Gracefully

```yaml
hooks:
  on_error:
    script: |
      try:
        # Attempt notification
        send_alert(error)
      except Exception as e:
        # Don't let hook failure mask original error
        print(f"Hook notification failed: {e}", file=sys.stderr)
    language: python
```

### 3. Use Appropriate Languages

```yaml
# Shell for simple commands
hooks:
  on_start:
    script: echo "Starting at $(date)"
    language: shell

# Python for complex logic
hooks:
  on_end:
    script: |
      import json
      from datetime import datetime
      
      report = {
        'completed_at': datetime.now().isoformat(),
        'duration': ctx.duration,
        'status': 'success'
      }
      
      with open(f'{ctx.output_path}/report.json', 'w') as f:
        json.dump(report, f, indent=2)
    language: python
```

### 4. Document Hook Behavior

```yaml
hooks:
  on_start:
    # This hook validates the target is reachable before starting
    # If validation fails, the workflow will not execute
    script: |
      import socket
      try:
        socket.gethostbyname('${{ inputs.target }}')
        print(f"✓ Target {ctx.inputs['target']} is reachable")
      except:
        print(f"✗ Target {ctx.inputs['target']} cannot be resolved")
        sys.exit(1)
    language: python
```

### 5. Avoid Side Effects in Read-Only Hooks

```yaml
# Good - on_line just observes
hooks:
  on_line:
    script: |
      if 'ERROR' in line:
        print(f"Warning: Error detected in output")
    language: python

# Bad - on_line modifies state
hooks:
  on_line:
    script: |
      # Don't do this - race conditions!
      with open('output.txt', 'a') as f:
        f.write(line)
    language: python
```

## Advanced Examples

### Multi-Stage Deployment with Hooks

```yaml
name: Multi-Stage Deployment

hooks:
  on_start:
    script: python deployment_started.py --stage ${{ inputs.stage }}
    language: shell
  
  on_error:
    script: |
      import sys
      print(f"DEPLOYMENT FAILED AT STAGE: {ctx.current_job}")
      # Rollback logic
      rollback_deployment(ctx.current_job)
      sys.exit(1)
    language: python

jobs:
  validate:
    hooks:
      on_success:
        script: echo "✓ Validation passed"
        language: shell
    steps:
      - name: Validate configuration
        run: python validate_config.py
  
  deploy_stage:
    needs: [validate]
    hooks:
      on_start:
        script: python pre_deploy_checks.py
        language: shell
      on_success:
        script: python post_deploy_verify.py
        language: shell
    steps:
      - name: Deploy to Kubernetes
        run: kubectl apply -f deployment.yml
  
  smoke_test:
    needs: [deploy_stage]
    hooks:
      on_failure:
        script: |
          print("Smoke tests failed - initiating rollback")
          rollback()
        language: python
    steps:
      - name: Run smoke tests
        run: python smoke_tests.py
```

## See Also

- [Workflows](workflows.md) - Workflow configuration
- [Jobs & Steps](jobs-steps.md) - Job and step configuration
- [Templates](templates.md) - Template variables in hooks
