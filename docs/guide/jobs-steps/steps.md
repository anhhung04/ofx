# Steps

Steps are the smallest unit of execution in an OFX workflow. Each step runs a command, script, or code block, and can have its own environment, outputs, and error handling.

---

## Step Syntax
```yaml
name: Example Workflow
jobs:
  example:
    name: Example Job
    steps:
      - name: Run Script
        run: ./myscript.sh
        env:
          VAR: value
        timeout: 10
        outputs:
          result: "${{ step.stdout }}"
        continue_on_error: true
```

---

## Step Fields
- `name`: (optional) Description of the step
- `run`: Command, script, or code to execute
- `language`: (optional) Language for code blocks (e.g., python)
- `env`: (optional) Environment variables
- `timeout`: (optional) Max time in minutes
- `outputs`: (optional) Exported values from this step
- `continue_on_error`: (optional) Continue even if this step fails
- `run_if`: (optional) Conditional execution (e.g., `failure()`)

---

## Advanced Usage
- Use `script:` to run inline Python code
- Use `script_file:` to execute an existing Python file (resolved relative to the workflow directory)
- Use `outputs:` to pass data between steps and jobs
- Use `run_if:` for conditional logic (see [Hooks & Conditions](../hooks.md))

---

## Python Scripts and Inter-Job Communication

Steps can execute inline Python code using the `script` field. Python scripts have access to workflow context, environment variables, and special functions for inter-job communication.

### Available Variables in Scripts

Python scripts automatically have access to:
- `__job__`: The current job model object
- `__step__`: The current step model object  
- `__workflow__`: The current workflow model object
- `__ctx__`: The run context object

### Channel Communication Functions

Scripts can communicate between jobs using channel functions:

- `publish(channel, data)`: Publish data to a named channel
- `subscribe(channel)`: Returns a generator that yields data when it changes (auto-emit)
- `wait_for(channel, condition, timeout=60)`: Wait for data matching a condition

### Example: Inter-Job Communication
```yaml
name: Channel Communication Example
jobs:
  producer:
    steps:
      - name: Send data
        script: |
          publish('results', {'status': 'complete', 'data': [1, 2, 3]})
          
  consumer:
    needs: producer
    steps:
      - name: Receive data
        script: |
          # Wait for data
          data = wait_for('results', lambda d: d.get('status') == 'complete')
          print(f"Received: {data}")
          
      - name: Subscribe to changes
        script: |
          # Subscribe returns a generator
          gen = subscribe('results')
          for update in gen:
              print(f"Update: {update}")
              if update.get('status') == 'complete':
                  break
```

Channels are scoped to the workflow level and allow jobs to coordinate asynchronously.

---

## See Also
- [Jobs](jobs.md)
- [Outputs](outputs.md)
- [Script files](script-file.md)