# Job Registry System

The OFX job registry uses the **Adapter Pattern** to support multiple storage backends for job state management during workflow execution.

## Architecture

The registry system consists of:

1. **Abstract Base Class** (`JobRegistryAdapter`) - Defines the interface all adapters must implement
2. **Concrete Adapters** - Implementations for different storage backends:
   - `MemoryJobRegistry` - In-memory storage (default)
   - `FileJobRegistry` - File-based persistent storage
   - `RedisJobRegistry` - Redis-based distributed storage (optional)
3. **Factory** (`create_job_registry`) - Creates registry instances based on configuration

## Available Backends

### Memory (Default)
- **Storage**: In-memory Python dictionary
- **Persistence**: None (data lost on process exit)
- **Use Case**: Single-process workflows, development, testing
- **Dependencies**: None (built-in)

```python
from ofx.runner.core import create_job_registry

registry = create_job_registry("memory")
```

### File
- **Storage**: JSON file on disk
- **Persistence**: Yes (survives process restarts)
- **Use Case**: Single-process workflows with persistence needs
- **Dependencies**: `aiofiles`, `filelock` (included in base dependencies)

```python
from ofx.runner.core import create_job_registry

# Use default path (~/.local/share/ofx/job_registry.json)
registry = create_job_registry("file")

# Or specify custom path
registry = create_job_registry("file", filepath="/tmp/my_jobs.json")
```

### Redis (Optional)
- **Storage**: Redis server
- **Persistence**: Configurable (Redis persistence settings)
- **Use Case**: Distributed workflows, multiple processes, production
- **Dependencies**: `redis>=5.0.0` (install with `pip install ofx[redis]`)

```python
from ofx.runner.core import create_job_registry

# Basic usage
registry = create_job_registry("redis")

# With custom configuration
registry = create_job_registry(
    "redis",
    host="redis.example.com",
    port=6379,
    db=0,
    password="secret",
    prefix="myapp:jobs:"
)
```

## Usage

### Basic Operations

All registry adapters implement the same async interface:

```python
import asyncio
from ofx.runner.core import create_job_registry, cleanup_registry

async def example():
    # Create registry
    registry = create_job_registry("memory")
    
    # Store job data
    await registry.set("job1", {
        "name": "Build",
        "status": "running",
        "steps": []
    })
    
    # Retrieve job data
    job = await registry.get("job1")
    print(job)  # {'name': 'Build', 'status': 'running', 'steps': []}
    
    # Update job data
    await registry.update("job1", {"status": "completed"})
    
    # Check existence
    exists = await registry.exists("job1")  # True
    
    # Get all jobs
    all_jobs = await registry.get_all()
    
    # Delete job
    await registry.delete("job1")
    
    # Clean up resources
    await cleanup_registry(registry)

asyncio.run(example())
```

### Configuration via Settings

Configure the registry backend using environment variables:

```bash
# Use memory backend (default)
export OFX_REGISTRY_BACKEND=memory

# Use file backend with custom path
export OFX_REGISTRY_BACKEND=file
export OFX_REGISTRY_FILE_PATH=/tmp/jobs.json

# Use Redis backend
export OFX_REGISTRY_BACKEND=redis
export OFX_REGISTRY_REDIS_HOST=localhost
export OFX_REGISTRY_REDIS_PORT=6379
export OFX_REGISTRY_REDIS_DB=0
export OFX_REGISTRY_REDIS_PASSWORD=secret
export OFX_REGISTRY_REDIS_PREFIX=ofx:job:
```

Or create a `.env` file:

```env
OFX_REGISTRY_BACKEND=redis
OFX_REGISTRY_REDIS_HOST=redis.example.com
OFX_REGISTRY_REDIS_PORT=6379
```

Then use the settings-based factory:

```python
from ofx.runner.core import create_registry_from_settings

# Automatically uses settings configuration
registry = create_registry_from_settings()
```

### Using with WorkflowRunner

The `WorkflowRunner` now accepts an optional `registry` parameter:

```python
from ofx.runner import WorkflowRunner, RunContext
from ofx.runner.core import create_job_registry

# Create custom registry
registry = create_job_registry("redis", host="redis.example.com")

# Pass to WorkflowRunner
runner = WorkflowRunner(
    workflow=my_workflow,
    ctx=RunContext(),
    registry=registry
)

# If no registry is provided, uses default memory registry
runner = WorkflowRunner(workflow=my_workflow, ctx=RunContext())
```

## Installation

### Base Installation
```bash
pip install ofx
```
Includes support for memory and file backends.

### With Redis Support
```bash
pip install ofx[redis]
```

### Development Installation
```bash
# Clone repository
git clone https://github.com/your-org/ofx.git
cd ofx

# Install with all optional dependencies
pip install -e ".[redis,test,docs]"
```

## Creating Custom Adapters

To create a custom registry adapter:

1. Inherit from `JobRegistryAdapter`
2. Implement all abstract methods
3. Register in your application

```python
from ofx.runner.core.registries import JobRegistryAdapter

class DatabaseJobRegistry(JobRegistryAdapter):
    """Custom database-based registry"""
    
    def __init__(self, connection_string: str):
        self.conn = create_connection(connection_string)
    
    async def set(self, key: str, value: dict) -> None:
        # Implementation
        pass
    
    async def get(self, key: str) -> dict | None:
        # Implementation
        pass
    
    # ... implement other methods
```

## Performance Considerations

### Memory Registry
- **Fastest**: No I/O overhead
- **Limited**: By available RAM
- **Best for**: Small workflows, testing

### File Registry
- **Moderate**: File I/O overhead
- **Scalable**: Limited by disk space
- **Best for**: Medium workflows, single-machine deployments

### Redis Registry
- **Network overhead**: Depends on Redis location
- **Highly scalable**: Distributed storage
- **Best for**: Large workflows, distributed systems, production

## Thread Safety

All registry adapters are designed for async/await usage:

- **Memory**: Thread-safe for single process
- **File**: Uses file locking for concurrent access
- **Redis**: Inherently supports concurrent access

## Testing

Run registry tests:

```bash
# Test all adapters except Redis
pytest tests/test_job_registry.py

# Test including Redis (requires Redis server)
pytest tests/test_job_registry.py --redis
```

## Troubleshooting

### Redis Connection Issues

```python
# Test Redis connectivity
import redis.asyncio as aioredis

async def test_redis():
    client = aioredis.Redis(host='localhost', port=6379)
    await client.ping()
    print("Redis OK")

asyncio.run(test_redis())
```

### File Permission Issues

Ensure the directory for file-based registry exists and is writable:

```bash
mkdir -p ~/.local/share/ofx
chmod 755 ~/.local/share/ofx
```

### Import Errors

If `RedisJobRegistry` import fails:

```bash
pip install redis>=5.0.0
# or
pip install ofx[redis]
```

## API Reference

### JobRegistryAdapter (Abstract Base Class)

```python
class JobRegistryAdapter(ABC):
    async def set(key: str, value: dict) -> None
    async def get(key: str) -> dict | None
    async def update(key: str, updates: dict) -> None
    async def delete(key: str) -> bool
    async def exists(key: str) -> bool
    async def get_all() -> dict[str, dict]
    async def clear() -> None
    async def close() -> None
```

### Factory Functions

```python
def create_job_registry(
    backend: Literal["memory", "file", "redis"],
    **kwargs
) -> JobRegistryAdapter

def create_registry_from_settings() -> JobRegistryAdapter

async def cleanup_registry(registry: JobRegistryAdapter) -> None
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OFX_REGISTRY_BACKEND` | `memory` | Registry type: memory, file, or redis |
| `OFX_REGISTRY_FILE_PATH` | `~/.local/share/ofx/job_registry.json` | File path for file backend |
| `OFX_REGISTRY_REDIS_HOST` | `localhost` | Redis server host |
| `OFX_REGISTRY_REDIS_PORT` | `6379` | Redis server port |
| `OFX_REGISTRY_REDIS_DB` | `0` | Redis database number |
| `OFX_REGISTRY_REDIS_PASSWORD` | None | Redis password |
| `OFX_REGISTRY_REDIS_PREFIX` | `ofx:job:` | Redis key prefix |
