# Best Practices for Interactive Mode

## Set Appropriate Timeouts
Always set timeouts for interactive sessions to prevent hanging:
```yaml
- name: Interactive Session
  module: shell
  with:
    cmd: bash
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
        module: shell
        with:
          cmd: |
            ./setup.sh
            ./process.sh
      - name: Debug Session
        module: shell
        with:
          cmd: bash
        interactive: true
        if: failure()  # Only run if previous step failed
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
        module: shell
        with:
          cmd: ./prepare.sh
  interact:
    name: Interactive Session
    needs: prepare  # Sequential execution
    steps:
      - name: Launch interactive shell
        module: shell
        with:
          cmd: bash
        interactive: true
  cleanup:
    name: Cleanup
    needs: interact  # Runs after interaction
    steps:
      - name: Run cleanup script
        module: shell
        with:
          cmd: ./cleanup.sh
```
