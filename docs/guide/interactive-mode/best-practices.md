# Best Practices for Interactive Mode

## Set Appropriate Timeouts
Always set timeouts for interactive sessions to prevent hanging:
```yaml
- name: Interactive Session
  run: bash
  interactive: true
  timeout: 15  # 15 minutes timeout
```

## Use for Debugging
Interactive mode is perfect for debugging workflow issues:
```yaml
jobs:
  debug:
    steps:
      - name: Run Commands
        run: |
          ./setup.sh
          ./process.sh
      - name: Debug Session
        run: bash
        interactive: true
        run_if: failure()  # Only run if previous step failed
```

## Combine with Hooks
Use hooks to prepare the environment before interactive sessions:
```yaml
jobs:
  interactive_session:
    hooks:
      on_start:
        run: echo "Starting interactive session..."
        language: shell
    steps:
      - name: Interactive Tool
        run: ./custom_tool
        interactive: true
```

## Sequential Dependencies
Ensure interactive jobs run sequentially:
```yaml
name: Interactive Workflow
jobs:
  prepare:
    name: Preparation
    steps:
      - name: Run preparation script
        run: ./prepare.sh
  interact:
    name: Interactive Session
    needs: prepare  # Sequential execution
    steps:
      - name: Launch interactive shell
        run: bash
        interactive: true
  cleanup:
    name: Cleanup
    needs: interact  # Runs after interaction
    steps:
      - name: Run cleanup script
        run: ./cleanup.sh
```
