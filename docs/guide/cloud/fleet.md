# Fleet Mode (Distributed Execution)

Fleet mode distributes targets across multiple VPS instances for parallel execution — similar to [Axiom](https://github.com/pry0cc/axiom). Each instance gets a chunk of targets, runs the job steps independently, and is destroyed when done.

## How It Works

```
                          ┌─────────────────────────────────┐
                          │     CloudMatrixJobRunner        │
                          │  (expands fleet combinations)   │
                          └──────────┬──────────────────────┘
                                     │ spawns N CloudJobRunners
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
         ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
         │ CloudJob #0  │   │ CloudJob #1  │   │ CloudJob #2  │
         │ VPS: nyc-abc │   │ VPS: nyc-def │   │ VPS: nyc-ghi │
         │ chunk_0.txt  │   │ chunk_1.txt  │   │ chunk_2.txt  │
         └──────────────┘   └──────────────┘   └──────────────┘
              ↓                   ↓                   ↓
         [provision]         [provision]         [provision]
         [upload chunk]      [upload chunk]      [upload chunk]
         [run steps]         [run steps]         [run steps]
         [download out]      [download out]      [download out]
         [destroy VPS]       [destroy VPS]       [destroy VPS]
```

All fleet instances run **in parallel** (controlled by `max_parallel`).

## Quick Start

```yaml
name: fleet-scan
call:
  inputs:
    targets:
      required: true

jobs:
  scan:
    cloud: do-small
    strategy:
      fleet:
        count: 5
        input: "{{ inputs.targets }}"
        distribution: chunk
    steps:
      - run: apt install nmap -y
      - run: |
          nmap -iL $FLEET_INPUT_FILE \
               -oA output/scan-$FLEET_INDEX
```

```bash
ofx x run fleet-scan -i "targets=targets.txt"
```

## Fleet Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `count` | int | **required** | Number of fleet instances to create |
| `input` | string/list | `""` | Targets to distribute (file path, IPs, CIDRs, or mixed) |
| `distribution` | string | `"chunk"` | How to split targets across instances |
| `expand_cidrs` | bool | `true` | Expand CIDR ranges to individual IPs before splitting |
| `exclude` | list | `[]` | IPs or CIDRs to exclude from distribution |

### Distribution methods

| Method | Description | Best for |
|--------|-------------|----------|
| `chunk` | Split into N sequential, equal-sized chunks | General scanning |
| `round-robin` | Deal targets round-robin across instances | Even distribution with mixed target sizes |
| `subnet` | Group by /24 subnet, assign to least-full bucket | Network-aware scanning |
| `line` | One line per instance (count = number of lines) | When each line is a complete task |

### Input formats

The fleet input parser supports these formats (and combinations of them):

| Format | Example |
|--------|---------|
| Single IP | `192.168.1.1` |
| CIDR | `10.0.0.0/24` (expands to 254 IPs if `expand_cidrs: true`) |
| IP range | `10.0.0.1-10.0.0.50` |
| Short range | `10.0.0.1-50` |
| Hostname | `server1.example.com` |
| Comma-separated | `10.0.0.1,10.0.0.2,host.com` |
| File path | `targets.txt` (one target per line) |
| Mixed list | `[10.0.0.0/24, targets.txt, host.com]` |

### Auto-reduction

If the number of targets is less than `count`, OFX automatically reduces the fleet size to match the number of targets:

```
Fleet: reducing instance count from 10 to 3 (only 3 targets available)
```

## Variables Available in Fleet Jobs

### Template variables (Jinja2)

| Variable | Example value | Description |
|----------|---------------|-------------|
| `{{ matrix.fleet_index }}` | `0` | 0-based instance index |
| `{{ matrix.fleet_total }}` | `5` | Total fleet instances |
| `{{ matrix.fleet_input_file }}` | `/tmp/ofx_fleet_0pnxa5q9/fleet_chunk_0.txt` | Local path to chunk file |
| `{{ matrix.fleet_target_count }}` | `42` | Number of targets in this chunk |
| `{{ remote_fleet_input_file }}` | `/tmp/.run-77f279a4/fleet_targets.txt` | Remote path to chunk file on VPS |

Fleet vars are also available under the `fleet` namespace: `{{ fleet.fleet_index }}`, etc.

### Shell environment variables

| Env var | Description |
|---------|-------------|
| `$FLEET_INPUT_FILE` | Remote path to the target chunk file |
| `$FLEET_INDEX` | Instance index (0-based) |
| `$FLEET_TOTAL` | Total number of fleet instances |
| `$FLEET_TARGET_COUNT` | Number of targets in this chunk |

Both template and shell syntaxes work interchangeably for fleet vars.

## Chunk File Upload

For each fleet instance:

1. OFX writes the target chunk to a local temp file in `/tmp/ofx_fleet_*/fleet_chunk_N.txt`
2. A `CloudJobRunner` is created for this combination
3. During `_do_run()`, the chunk file is uploaded to the VPS at `<work_dir>/fleet_targets.txt`
4. The `FLEET_INPUT_FILE` env var is rewritten to point to the **remote** path
5. Steps can then read targets from `$FLEET_INPUT_FILE` or `{{ matrix.fleet_input_file }}`

After all combinations complete, local chunk files and their parent temp directory are cleaned up.

## Parallelism Control

### max_parallel

Controls how many VPS instances are provisioned and run simultaneously:

```yaml
strategy:
  max_parallel: 3       # Only 3 VPS at a time
  fleet:
    count: 10
    input: targets.txt
```

Without `max_parallel`, all fleet instances run concurrently (default is unlimited).

This is useful for:
- Respecting cloud provider rate limits
- Controlling costs (don't spin up 50 VPS at once)
- Avoiding target IDS/IPS detection from too many simultaneous sources

### Execution model

Fleet jobs use `asyncio.create_task` + `asyncio.gather` with a semaphore. All SSH operations (`PostSSH.run()`, `upload()`, `download()`) are wrapped in `asyncio.to_thread()` to prevent blocking the event loop. This means:

- VPS provisioning happens concurrently
- SSH login waiting happens concurrently
- Step execution on different VPS happens concurrently
- Output download and VPS destruction happen concurrently

## Combined Matrix + Fleet

You can use both `matrix` and `fleet` together. OFX creates the Cartesian product:

```yaml
jobs:
  scan:
    cloud: do-small
    strategy:
      matrix:
        tool: [nmap, masscan]
      fleet:
        count: 3
        input: targets.txt
    steps:
      - run: |
          {{ matrix.tool }} -iL $FLEET_INPUT_FILE \
            -oA output/{{ matrix.tool }}-$FLEET_INDEX
```

This creates `2 tools x 3 chunks = 6 VPS instances`, each running one tool against one chunk.

## Static Fleet

Use pre-existing hosts without cloud provisioning:

```yaml
jobs:
  scan:
    cloud:
      provider: static
      hosts:
        - host: 10.0.0.1
          ssh_user: root
        - host: 10.0.0.2
          ssh_user: root
        - host: 10.0.0.3
          ssh_user: operator
    strategy:
      fleet:
        count: 3
        input: targets.txt
        distribution: round-robin
    steps:
      - run: masscan -iL $FLEET_INPUT_FILE -p 1-65535 --rate 10000
```

Static fleet instances are never destroyed — only SSH connectivity is verified.

## Complete Example

Distributed nmap scan with result aggregation:

```yaml
name: distributed-recon
call:
  inputs:
    targets:
      required: true
      type: string
    fleet_size:
      required: false
      default: 5

jobs:
  fleet-scan:
    name: Fleet Scan
    cloud: do-small
    strategy:
      max_parallel: 5
      fleet:
        input: "{{ inputs.targets }}"
        distribution: round-robin
        count: "{{ inputs.fleet_size }}"
    env:
      NONINTERACTIVE: "1"
    steps:
      - name: install-tools
        run: apt-get update && apt-get install -y nmap

      - name: scan
        run: |
          echo "Instance $FLEET_INDEX scanning $FLEET_TARGET_COUNT targets"
          nmap -iL $FLEET_INPUT_FILE -sV \
               -oA output/scan-$FLEET_INDEX
          echo "Scan complete"

      - name: summary
        run: |
          echo "=== Results ==="
          if [ -f output/scan-$FLEET_INDEX.gnmap ]; then
            grep "open" output/scan-$FLEET_INDEX.gnmap | wc -l
          fi
```

```bash
# Run with 5 fleet instances
ofx x run distributed-recon -i "targets=targets.txt" -i "fleet_size=5"

# Results downloaded to:
# /tmp/.tmp_r_.../run_.../fleet-scan_0/  (instance 0 output)
# /tmp/.tmp_r_.../run_.../fleet-scan_1/  (instance 1 output)
# ...
```

## Troubleshooting

### "Fleet: reducing instance count from N to M"

This means fewer targets are available than the requested `count`. Reduce `count` or add more targets.

### Fleet chunk file not found on VPS

If `$FLEET_INPUT_FILE` is empty or the file doesn't exist, check:

1. The `input` path is correct and accessible locally
2. The upload didn't fail (check logs for "Failed to upload fleet input")
3. The step isn't running before the upload completes (shouldn't happen — upload is in `_do_run` before steps)

### Instances not running in parallel

Verify your logs show concurrent provisioning timestamps. If instances provision sequentially, ensure you're using the latest OFX version where SSH operations are non-blocking (`asyncio.to_thread`).
