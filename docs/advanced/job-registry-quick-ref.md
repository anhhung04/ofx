# Job Registry Quick Reference

## Installation

```bash
# Base installation (memory + file backends)
pip install ofx

# With Redis support
pip install ofx[redis]
```

## Basic Usage

```python
from ofx.runner.core import create_job_registry, cleanup_registry

async def main():
    # Create registry
    registry = create_job_registry("memory")
    
    # Operations
    await registry.set("job1", {"status": "running"})
    job = await registry.get("job1")
    await registry.update("job1", {"status": "completed"})
    await registry.delete("job1")
    
    # Cleanup
    await cleanup_registry(registry)
```

## Backend Options

| Backend | Persistence | Dependencies | Use Case |
|---------|-------------|--------------|----------|
| `memory` | No | None | Testing, dev |
| `file` | Yes | Built-in | Single machine |
| `redis` | Yes | redis>=5.0 | Distributed |

## Configuration

### Via Code

```python
# Memory (default)
registry = create_job_registry("memory")

# File
registry = create_job_registry("file", filepath="/tmp/jobs.json")

# Redis
registry = create_job_registry("redis", host="localhost", port=6379)
```

### Via Environment Variables

```bash
# Memory
export OFX_REGISTRY_BACKEND=memory

# File
export OFX_REGISTRY_BACKEND=file
export OFX_REGISTRY_FILE_PATH=/tmp/jobs.json

# Redis
export OFX_REGISTRY_BACKEND=redis
export OFX_REGISTRY_REDIS_HOST=localhost
export OFX_REGISTRY_REDIS_PORT=6379
export OFX_REGISTRY_REDIS_DB=0
export OFX_REGISTRY_REDIS_PASSWORD=secret
```

### Using Settings

```python
from ofx.runner.core import create_registry_from_settings

# Auto-configures from environment
registry = create_registry_from_settings()
```

## WorkflowRunner Integration

```python
from ofx.runner import WorkflowRunner, RunContext
from ofx.runner.core import create_job_registry

# Custom registry
registry = create_job_registry("redis")
runner = WorkflowRunner(workflow, RunContext(), registry=registry)

# Default (memory)
runner = WorkflowRunner(workflow, RunContext())
```

## API Methods

All methods are async:

```python
await registry.set(key, value)                  # Store data
await registry.get(key)                         # Retrieve data
await registry.update(key, updates)             # Update fields
await registry.delete(key)                      # Remove data
await registry.exists(key)                      # Check existence
await registry.get_all()                        # Get all entries
await registry.clear()                          # Clear all
await registry.close()                          # Close connections
```

## Examples

See:
- `/workspaces/ofx/examples/job_registry_example.py`
- `/workspaces/ofx/docs/advanced/job-registry.md`
- `/workspaces/ofx/tests/test_job_registry.py`

## Common Patterns

### Workflow with File Persistence

```python
registry = create_job_registry("file", filepath="~/.ofx/workflow.json")
runner = WorkflowRunner(workflow, ctx, registry=registry)
result = await runner.run()
await cleanup_registry(registry)
```

### Distributed Workflow with Redis

```python
registry = create_job_registry("redis", host="redis-cluster.local")
runner = WorkflowRunner(workflow, ctx, registry=registry)
result = await runner.run()
await cleanup_registry(registry)
```

### Testing with In-Memory

```python
@pytest.fixture
async def registry():
    reg = create_job_registry("memory")
    yield reg
    await cleanup_registry(reg)

async def test_workflow(registry):
    runner = WorkflowRunner(workflow, ctx, registry=registry)
    result = await runner.run()
    assert result.status == "completed"
```
