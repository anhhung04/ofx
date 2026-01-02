# Hooks System

The hook system allows you to execute custom code at various lifecycle points during workflow, job, and step execution. Hooks propagate conditionally through the execution hierarchy.

## Hook Types

### Lifecycle Hooks

Execute at specific points in the execution lifecycle:

- `before_init` - Before initialization
- `on_init` - During initialization
- `on_start` - When execution starts
- `on_iter` - On each iteration (for loops)
- `on_end` - When execution ends
- `before_run` - Before running
- `after_run` - After running

### Status Hooks

Execute based on execution status:

- `on_success` - When execution succeeds
- `on_failure` - When execution fails
- `on_error` - When an error occurs
- `on_cancel` - When execution is cancelled

### Command Hooks

Execute during command execution:

- `on_cmd` - Before command execution
- `on_cmd_done` - After command completion
- `on_line` - For each line of output

## Hook Structure

```yaml
hooks:
  hook_name:
    script: "script content"
```

### Single-line Hook

```yaml
hooks:
  on_start:
    script: echo "Starting execution"
    language: shell
```

### Multi-line Hook

```yaml
hooks:
  on_success:
    script: |
      import datetime
      print(f"Completed at {datetime.now()}")
      print(f"Duration: {ctx.duration} seconds")
```

## Hook Propagation

Hooks propagate **conditionally** through the hierarchy: **Step → Job → Workflow**

### Propagation Rules

1. **Step with hooks**: Step hooks execute, then propagate to Job, then Workflow
2. **Step without hooks**: Job hooks execute, then propagate to Workflow
3. **Job without hooks**: Only Workflow hooks execute

### Example

```yaml
name: Hook Propagation Example

hooks:
  on_start:
    script: echo "Workflow started"  # Executes for all
    language: shell

jobs:
  job1:
    hooks:
      on_start:
        script: echo "Job1 started"  # Executes + propagates to workflow
        language: shell
    steps:
      - name: Step with hook
        run: echo "Hello"
        hooks:
          on_start:
            script: echo "Step started"  # Executes + propagates to job + workflow
            language: shell
      
      - name: Step without hook
        run: echo "World"
        # Job hook executes + propagates to workflow
```

**Execution order for first step:**
1. Step's `on_start` hook
2. Job's `on_start` hook (propagated)
3. Workflow's `on_start` hook (propagated)
4. Step executes
5. Hooks in reverse for `on_end`

## Hook Scopes

### Workflow-Level Hooks

Apply to the entire workflow:

```yaml
name: My Workflow

hooks:
  on_start:
    script: |
      print("=== Workflow Starting ===")
      print(f"Target: {ctx.inputs['target']}")
      print(f"Run ID: {ctx.run_id}")
  
  on_success:
    script: python notify.py --status success --target ${{ inputs.target }}
    language: shell
  
  on_error:
    script: |
      import sys
      print(f"ERROR: {error}", file=sys.stderr)
      # Send alert
      import requests
      requests.post('https://alerts.example.com', json={'error': str(error)})
    language: python

jobs:
  # ... job definitions
```

### Job-Level Hooks

Apply to specific jobs:

```yaml
jobs:
  critical_scan:
    hooks:
      on_start:
        script: echo "Starting critical scan - alerting team"
        language: shell
      
      on_failure:
        script: python alert_team.py --severity high --job critical_scan
        language: shell
      
      on_success:
        script: python log_success.py --job critical_scan
        language: shell
    
    steps:
      - name: Scan
        run: nmap -sV ${{ inputs.target }}
```

### Step-Level Hooks

Apply to individual steps:

```yaml
steps:
  - name: Critical operation
    run: python critical.py
    hooks:
      on_start:
        script: echo "Starting critical operation at $(date)"
        language: shell
      
      on_cmd:
        script: |
          print(f"Executing command: {command}")
          print(f"Working directory: {os.getcwd()}")
      
      on_line:
        script: |
          # Process each line of output
          print(f"OUTPUT: {line.strip()}")
      
      on_success:
        script: echo "Critical operation succeeded"
        language: shell
      
      on_error:
        script: |
          print(f"CRITICAL ERROR: {error}")
          # Emergency notification
```

## Available Context in Hooks

Hooks have access to execution context:

### Python Hooks

```yaml
hooks:
  on_start:
    script: |
      # Access context variables
      print(f"Run ID: {ctx.run_id}")
      print(f"Inputs: {ctx.inputs}")
      print(f"Secrets: {ctx.secrets}")
      print(f"Output path: {ctx.output_path}")
      print(f"Environment: {ctx.envs}")
      
      # For step hooks
      print(f"Step name: {step.name}")
      print(f"Command: {step.run}")
      
      # For error hooks
      print(f"Error: {error}")
      print(f"Error type: {type(error)}")
    language: python
```

### Shell Hooks

```yaml
hooks:
  on_start:
    script: |
      echo "Target: ${{ inputs.target }}"
      echo "Output: ${{ ctx.output_path }}"
      echo "Run ID: ${{ ctx.run_id }}"
    language: shell
```

## Common Use Cases

### 1. Logging and Monitoring

```yaml
hooks:
  on_start:
    script: |
      import logging
      logging.basicConfig(level=logging.INFO)
      logger = logging.getLogger('workflow')
      logger.info(f"Workflow started: {ctx.inputs}")
    language: python
  
  on_end:
    script: |
      import logging
      logger = logging.getLogger('workflow')
      logger.info(f"Workflow completed in {ctx.duration}s")
    language: python
```

### 2. Notifications

```yaml
hooks:
  on_success:
    script: |
      import requests
      requests.post(
        'https://hooks.slack.com/services/YOUR/WEBHOOK/URL',
        json={
          'text': f'✅ Workflow completed successfully for {ctx.inputs["target"]}'
        }
      )
    language: python
  
  on_error:
    script: |
      import requests
      requests.post(
        'https://hooks.slack.com/services/YOUR/WEBHOOK/URL',
        json={
          'text': f'❌ Workflow failed: {error}'
        }
      )
    language: python
```

### 3. Resource Cleanup

```yaml
hooks:
  on_end:
    script: |
      import os
      import shutil
      
      # Clean up temporary files
      temp_dir = '/tmp/workflow_temp'
      if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
      
      # Close connections
      # cleanup_resources()
    language: python
```

### 4. Pre-flight Checks

```yaml
hooks:
  before_run:
    script: |
      import os
      import sys
      
      # Check required tools
      tools = ['nmap', 'curl', 'python3']
      for tool in tools:
        if os.system(f'which {tool} > /dev/null 2>&1') != 0:
          print(f"ERROR: Required tool '{tool}' not found")
          sys.exit(1)
      
      # Check network connectivity
      if os.system('ping -c 1 8.8.8.8 > /dev/null 2>&1') != 0:
        print("ERROR: No network connectivity")
        sys.exit(1)
      
      print("✓ All pre-flight checks passed")
    language: python
```

### 5. Progress Tracking

```yaml
jobs:
  long_scan:
    hooks:
      on_line:
        script: |
          # Track progress from command output
          import re
          
          # Parse percentage from nmap output
          match = re.search(r'(\d+)% done', line)
          if match:
            progress = int(match.group(1))
            print(f"Progress: {progress}%")
            
            # Update external tracker
            # update_progress(ctx.run_id, progress)
    
    steps:
      - name: Full port scan
        run: nmap -p- -v ${{ inputs.target }}
```

### 6. Metrics Collection

```yaml
hooks:
  on_start:
    script: |
      import time
      ctx.start_time = time.time()
    language: python
  
  on_end:
    script: |
      import time
      duration = time.time() - ctx.start_time
      
      # Log metrics
      metrics = {
        'workflow': 'security_scan',
        'target': ctx.inputs['target'],
        'duration_seconds': duration,
        'status': 'success' if success else 'failed'
      }
      
      # Send to metrics service
      # send_metrics(metrics)
      print(f"Metrics: {metrics}")
    language: python
```

### 7. Dynamic Configuration

```yaml
hooks:
  on_init:
    script: |
      import json
      
      # Load dynamic configuration
      with open('config.json') as f:
        config = json.load(f)
      
      # Update context
      ctx.custom_config = config
      
      # Modify inputs based on config
      if config.get('aggressive_mode'):
        ctx.inputs['scan_speed'] = 'aggressive'
    language: python
```

### 8. Conditional Execution

```yaml
hooks:
  before_run:
    script: |
      import datetime
      
      # Only run during business hours
      hour = datetime.datetime.now().hour
      if hour < 9 or hour > 17:
        print("Scan not allowed outside business hours (9-17)")
        sys.exit(1)
      
      # Check if target is in allowed list
      allowed = ['192.168.1.0/24', 'test.example.com']
      if ctx.inputs['target'] not in allowed:
        print(f"Target {ctx.inputs['target']} not in allowed list")
        sys.exit(1)
    language: python
```

## Hook Best Practices

### 1. Keep Hooks Focused

```yaml
# Good - Single responsibility
hooks:
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
      - run: python validate_config.py
  
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
      - run: kubectl apply -f deployment.yml
  
  smoke_test:
    needs: [deploy_stage]
    hooks:
      on_failure:
        script: |
          print("Smoke tests failed - initiating rollback")
          rollback()
        language: python
    steps:
      - run: python smoke_tests.py
```

## See Also

- [Workflows](workflows.md) - Workflow configuration
- [Jobs & Steps](jobs-steps.md) - Job and step configuration
- [Templates](templates.md) - Template variables in hooks
