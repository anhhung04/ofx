# Job Registry Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      OFX Workflow Execution                      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       WorkflowRunner                             │
│  - Orchestrates job execution                                    │
│  - Manages job state via registry adapter                        │
│  - Supports matrix expansion                                     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ uses
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   RegistryAdapter (Abstract)                  │
│                                                                   │
│  Interface:                                                       │
│  ├── async set(key, value)                                       │
│  ├── async get(key) -> dict|None                                 │
│  ├── async update(key, updates)                                  │
│  ├── async delete(key) -> bool                                   │
│  ├── async exists(key) -> bool                                   │
│  ├── async get_all() -> dict                                     │
│  ├── async clear()                                                │
│  └── async close()                                                │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ MemoryJobRegistry│  │ FileJobRegistry │  │ RedisJobRegistry│
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ Storage:         │  │ Storage:         │  │ Storage:         │
│  - Python dict   │  │  - JSON file     │  │  - Redis server  │
│                  │  │  - File locking  │  │  - Distributed   │
│ Persistence: No  │  │ Persistence: Yes │  │ Persistence: Yes │
│                  │  │                  │  │                  │
│ Use Case:        │  │ Use Case:        │  │ Use Case:        │
│  - Development   │  │  - Single node   │  │  - Production    │
│  - Testing       │  │  - Persistence   │  │  - Distributed   │
│  - Prototyping   │  │  - Recovery      │  │  - High-scale    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
    ┌─────┐          ┌────────────┐      ┌────────────────┐
    │ RAM │          │ Filesystem │      │ Redis Cluster  │
    └─────┘          └────────────┘      └────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│                    Factory & Configuration                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  create_job_registry(backend, **kwargs) -> RegistryAdapter    │
│  ├── backend="memory" → MemoryJobRegistry()                      │
│  ├── backend="file" → FileJobRegistry(filepath)                  │
│  └── backend="redis" → RedisJobRegistry(host, port, ...)         │
│                                                                   │
│  create_registry_from_settings() -> RegistryAdapter           │
│  └── Uses environment variables for configuration                │
│                                                                   │
│  cleanup_registry(registry)                                       │
│  └── Closes connections and cleans up resources                  │
└─────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│                   Configuration Methods                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. Direct instantiation:                                         │
│     registry = create_job_registry("redis", host="localhost")    │
│                                                                   │
│  2. Environment variables:                                        │
│     export OFX_REGISTRY_BACKEND=redis                            │
│     export OFX_REGISTRY_REDIS_HOST=localhost                     │
│     registry = create_registry_from_settings()                   │
│                                                                   │
│  3. .env file:                                                    │
│     OFX_REGISTRY_BACKEND=file                                    │
│     OFX_REGISTRY_FILE_PATH=/tmp/jobs.json                        │
│     registry = create_registry_from_settings()                   │
└─────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│                      Data Flow Example                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. WorkflowRunner starts execution                              │
│     └─> Creates/receives RegistryAdapter                      │
│                                                                   │
│  2. Job planning phase                                            │
│     └─> await registry.set(key, metadata)                        │
│                                                                   │
│  3. Job execution                                                 │
│     ├─> await registry.update(key, {status: "running"})         │
│     ├─> Execute job steps                                         │
│     └─> await registry.update(key, {status: "completed"})       │
│                                                                   │
│  4. Status checking (from other jobs/stages)                      │
│     ├─> data = await registry.get(dependency_key)                │
│     └─> Check if dependencies met                                │
│                                                                   │
│  5. Workflow completion                                           │
│     ├─> all_jobs = await registry.get_all()                      │
│     ├─> Merge outputs                                             │
│     └─> await cleanup_registry(registry)                         │
└─────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│                   Adapter Pattern Benefits                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ✓ Decoupling: WorkflowRunner doesn't know storage details       │
│  ✓ Flexibility: Swap backends without changing workflow code     │
│  ✓ Extensibility: Easy to add new adapters (DB, S3, etc.)        │
│  ✓ Testability: Use memory adapter for fast unit tests           │
│  ✓ Scalability: Use Redis for distributed workflows              │
│  ✓ Persistence: Use file adapter for crash recovery              │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### Abstract Base Class (`RegistryAdapter`)
- Defines the contract all adapters must follow
- 8 async methods for CRUD operations
- Located: `src/ofx/runner/core/adapters/base.py`

### Memory Adapter (`MemoryJobRegistry`)
- Default implementation
- In-memory Python dictionary
- Zero dependencies, fastest performance
- Data lost on process exit

### File Adapter (`FileJobRegistry`)
- JSON file storage with file locking
- Survives process restarts
- Single-node deployments
- Default path: `~/.local/share/ofx/job_registry.json`

### Redis Adapter (`RedisJobRegistry`)
- Optional (requires `redis>=5.0.0`)
- Distributed storage
- Production-ready
- Supports clustering and replication

## Extension Points

To add a new adapter:

```python
from ofx.runner.registry import RegistryAdapter

class MyCustomAdapter(RegistryAdapter):
    async def set(self, key: str, value: dict) -> None:
        # Your implementation
        pass
    
    # ... implement other methods
```

Then register in factory:

```python
def create_job_registry(backend: str, **kwargs):
    if backend == "mycustom":
        return MyCustomAdapter(**kwargs)
    # ... existing backends
```
