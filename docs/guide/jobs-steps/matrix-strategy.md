# Matrix Strategy

Matrix strategy allows you to run a job multiple times with different parameter combinations. This is useful for testing across different configurations, environments, or platforms.

## Overview

A matrix strategy creates job variations by generating all combinations of the specified variables. Each combination runs as a separate job instance.

## Basic Usage

Define a matrix strategy using the `strategy` field in your job:

```yaml
name: Matrix Example
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu, windows, macos]
        python: ["3.10", "3.11", "3.12"]
    steps:
      - name: Run tests
        run: echo "Testing on {{ matrix.os }} with Python {{ matrix.python }}"
```

This creates 9 job instances (3 OS × 3 Python versions).

## Matrix Variables

Access matrix values using the `matrix` context variable:

```yaml
jobs:
  build:
    strategy:
      matrix:
        version: [1.0, 2.0, 3.0]
        arch: [x64, arm64]
    steps:
      - name: Build
        run: |
          echo "Building version {{ matrix.version }}"
          echo "Target architecture: {{ matrix.arch }}"
```

## Controlling Parallelism

### max_parallel

Limit the number of concurrent matrix jobs:

```yaml
jobs:
  deploy:
    strategy:
      max_parallel: 2  # Run only 2 matrix jobs at a time
      matrix:
        region: [us-east, us-west, eu-central, ap-south]
    steps:
      - run: echo "Deploying to {{ matrix.region }}"
```

Without `max_parallel`, all matrix jobs in a stage run concurrently (limited only by the global `workers` setting).

## Fail-Fast Behavior

Control whether matrix jobs should stop when one fails:

```yaml
jobs:
  test:
    strategy:
      fail_fast: true  # Default: stop all on first failure
      matrix:
        browser: [chrome, firefox, safari]
    steps:
      - run: test_browser.sh {{ matrix.browser }}
```

Set `fail_fast: false` to allow all matrix jobs to complete even if some fail:

```yaml
jobs:
  test:
    strategy:
      fail_fast: false  # Continue testing all browsers
      matrix:
        browser: [chrome, firefox, safari]
    steps:
      - run: test_browser.sh {{ matrix.browser }}
```

## Including Additional Combinations

Add specific combinations to the matrix:

```yaml
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu, windows]
        node: [14, 16]
        include:
          # Add macOS with Node 18
          - os: macos
            node: 18
          # Add Windows with Node 18 and experimental flag
          - os: windows
            node: 18
            experimental: true
    steps:
      - run: node --version
      - run: |
          if [ "{{ matrix.experimental }}" = "true" ]; then
            echo "Running experimental build"
          fi
```

The `include` field adds combinations that wouldn't be created by the base matrix.

## Excluding Combinations

Remove specific combinations from the matrix:

```yaml
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu, windows, macos]
        python: ["3.9", "3.10", "3.11"]
        exclude:
          # Python 3.9 not supported on macOS
          - os: macos
            python: "3.9"
          # Skip Windows + Python 3.11 (known issues)
          - os: windows
            python: "3.11"
    steps:
      - run: python --version
```

This creates 7 job instances instead of 9.

## Complex Example

Combining all features:

```yaml
name: Cross-Platform Build
jobs:
  build:
    strategy:
      max_parallel: 4
      fail_fast: false
      matrix:
        os: [ubuntu-20.04, ubuntu-22.04, windows-2022]
        compiler: [gcc, clang]
        build_type: [Debug, Release]
        exclude:
          # Windows doesn't use gcc in our setup
          - os: windows-2022
            compiler: gcc
        include:
          # Add macOS with clang only
          - os: macos-latest
            compiler: clang
            build_type: Release
    
    steps:
      - name: Checkout
        run: git clone https://github.com/example/repo.git
      
      - name: Configure
        run: |
          cmake -B build \
            -DCMAKE_BUILD_TYPE={{ matrix.build_type }} \
            -DCMAKE_C_COMPILER={{ matrix.compiler }}
      
      - name: Build
        run: cmake --build build --config {{ matrix.build_type }}
      
      - name: Test
        run: ctest --build-config {{ matrix.build_type }}
        working_directory: build
```

## Matrix with Dependencies

Matrix jobs respect dependencies like regular jobs:

```yaml
jobs:
  setup:
    steps:
      - run: echo "Setting up infrastructure"
  
  test:
    needs: setup
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - run: run_tests.sh --shard={{ matrix.shard }}/4
  
  report:
    needs: test
    steps:
      - run: echo "All test shards completed"
```

The `report` job waits for all matrix instances of `test` to complete.

## Dynamic Matrix Names

Use matrix values in job names for better visibility:

```yaml
jobs:
  test:
    name: "Test {{ matrix.os }} - Python {{ matrix.python }}"
    strategy:
      matrix:
        os: [ubuntu, windows]
        python: ["3.10", "3.11"]
    steps:
      - run: python --version
```

## Best Practices

1. **Keep matrices small**: Large matrices (>20 combinations) can be slow to execute
2. **Use max_parallel wisely**: Balance speed vs resource usage
3. **Set fail_fast appropriately**: 
   - `true` for quick feedback during development
   - `false` for comprehensive CI/CD testing
4. **Meaningful names**: Use matrix values in step/job names for clarity
5. **Clean up exclusions**: Document why certain combinations are excluded

## Limitations

- Matrix expansion happens before template resolution for job-level fields
- Matrix context is available in all job steps
- Outputs from matrix jobs are stored separately with expanded job IDs (e.g., `test_0`, `test_1`)
- Interactive mode is not supported for matrix jobs (interactive steps will be ignored)

## Advanced: Combining with Inputs

Matrix values can reference workflow inputs:

```yaml
name: Parameterized Matrix
dispatch:
  inputs:
    platforms:
      type: array
      default: ["linux", "windows"]

jobs:
  build:
    strategy:
      matrix:
        platform: "{{ inputs.platforms }}"
        config: [debug, release]
    steps:
      - run: echo "Building {{ matrix.config }} on {{ matrix.platform }}"
```

---

## Fleet Distribution

For cloud-based parallel execution, the `fleet` field within a matrix strategy distributes targets across multiple VPS instances. See [Fleet](../cloud/fleet.md) for details.

```yaml
jobs:
  scan:
    cloud: do-nyc
    strategy:
      matrix:
        ports: [80, 443]
      fleet:
        count: 3
        input: targets.txt
        distribution: chunk
    steps:
      - run: nmap -p {{ matrix.ports }} -iL $FLEET_INPUT_FILE
```

## Debugging Matrix Jobs

View expanded matrix jobs in logs:

```bash
ofx flow run my-workflow --debug
```

The logs will show each expanded job ID and its matrix values:

```
Expanded matrix job 'test' -> 'test_0' with matrix: {'os': 'ubuntu', 'python': '3.10'}
Expanded matrix job 'test' -> 'test_1' with matrix: {'os': 'ubuntu', 'python': '3.11'}
...
```
