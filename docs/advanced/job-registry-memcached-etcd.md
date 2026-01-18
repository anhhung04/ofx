# Memcached and etcd Registry Backends

## Overview

OFX now supports **Memcached** and **etcd** as additional registry backends, providing more options for distributed workflow coordination and caching.

## Memcached Registry

### Features

- **High-performance caching**: In-memory key-value store optimized for speed
- **Distributed**: Can be used across multiple nodes
- **Volatile storage**: Data is lost on server restart (use for temporary caching)
- **LRU eviction**: Automatically removes least-recently-used items when memory is full
- **Simple protocol**: Lightweight and fast

### Installation

```bash
# Install with Memcached support
pip install ofx[memcached]

# Or install the dependency directly
pip install aiomcache>=0.8.2
```

### Configuration

#### Environment Variables

```bash
export OFX_REGISTRY_BACKEND=memcached
export OFX_REGISTRY_MEMCACHED_HOST=localhost
export OFX_REGISTRY_MEMCACHED_PORT=11211
export OFX_REGISTRY_MEMCACHED_PREFIX=ofx:job:
```

#### Programmatic Configuration

```python
from ofx.runner.core import create_job_registry

# Create Memcached registry
registry = create_job_registry(
    "memcached",
    host="localhost",
    port=11211,
    prefix="ofx:job:",
    pool_size=2,
    pool_minsize=1
)
```

### Use Cases

- **High-speed temporary storage**: When you need fast read/write access
- **Distributed caching**: Share workflow state across multiple nodes
- **Session storage**: Temporary workflow execution data
- **Performance testing**: Quick iteration without persistence overhead

### Setup Memcached Server

```bash
# Ubuntu/Debian
sudo apt-get install memcached
sudo systemctl start memcached
sudo systemctl enable memcached

# macOS (Homebrew)
brew install memcached
brew services start memcached

# Docker
docker run -d --name memcached -p 11211:11211 memcached:latest
```

### Example Usage

```python
import asyncio
from ofx.runner.core import create_job_registry, cleanup_registry

async def main():
    # Create registry
    registry = create_job_registry("memcached")
    
    # Store workflow data
    await registry.set("workflow1", {
        "name": "exploit-scan",
        "status": "running",
        "start_time": "2026-01-18T10:00:00"
    })
    
    # Retrieve data
    workflow = await registry.get("workflow1")
    print(f"Workflow: {workflow['name']}, Status: {workflow['status']}")
    
    # Update status
    await registry.update("workflow1", {"status": "completed"})
    
    # Clean up
    await cleanup_registry(registry)

asyncio.run(main())
```

---

## etcd Registry

### Features

- **Strong consistency**: Distributed consensus via Raft algorithm
- **Persistent storage**: Data survives server restarts
- **Watch capabilities**: Monitor key changes in real-time
- **Distributed coordination**: Perfect for multi-node workflows
- **TTL support**: Automatic key expiration
- **Transaction support**: Atomic operations

### Installation

```bash
# Install with etcd support
pip install ofx[etcd]

# Or install the dependency directly
pip install etcd3>=0.12.0
```

### Configuration

#### Environment Variables

```bash
export OFX_REGISTRY_BACKEND=etcd
export OFX_REGISTRY_ETCD_HOST=localhost
export OFX_REGISTRY_ETCD_PORT=2379
export OFX_REGISTRY_ETCD_PREFIX=/ofx/job/
```

#### Programmatic Configuration

```python
from ofx.runner.core import create_job_registry

# Create etcd registry
registry = create_job_registry(
    "etcd",
    host="localhost",
    port=2379,  # gRPC port
    prefix="/ofx/job/",
    timeout=5
)
```

### Use Cases

- **Production workflows**: Strong consistency and persistence
- **Distributed systems**: Coordinate workflows across multiple nodes
- **Service discovery**: Track running workflows and their locations
- **Configuration management**: Centralized workflow configuration
- **Leader election**: Coordinate distributed job execution

### Setup etcd Server

```bash
# Ubuntu/Debian
sudo apt-get install etcd
sudo systemctl start etcd
sudo systemctl enable etcd

# macOS (Homebrew)
brew install etcd
brew services start etcd

# Docker
docker run -d \
  --name etcd \
  -p 2379:2379 \
  -p 2380:2380 \
  quay.io/coreos/etcd:latest \
  /usr/local/bin/etcd \
  --advertise-client-urls http://0.0.0.0:2379 \
  --listen-client-urls http://0.0.0.0:2379

# Docker Compose (production cluster)
# See: https://etcd.io/docs/latest/op-guide/container/
```

### Example Usage

```python
import asyncio
from ofx.runner.core import create_job_registry, cleanup_registry

async def main():
    # Create registry
    registry = create_job_registry("etcd")
    
    # Store job data
    await registry.set("job1", {
        "workflow": "recon-workflow",
        "status": "running",
        "node": "worker-01",
        "steps_completed": 3
    })
    
    # Store step data
    await registry.set("step1", {
        "job_id": "job1",
        "name": "port-scan",
        "status": "completed",
        "output": {"ports": [22, 80, 443]}
    })
    
    # Retrieve all data
    all_data = await registry.get_all()
    print(f"Total entries: {len(all_data)}")
    
    # Update job status
    await registry.update("job1", {
        "status": "completed",
        "steps_completed": 5
    })
    
    # Check existence
    if await registry.exists("job1"):
        print("Job found in registry")
    
    # Clean up
    await cleanup_registry(registry)

asyncio.run(main())
```

---

## Comparison Table

| Feature | Memcached | etcd | Redis | File | Memory |
|---------|-----------|------|-------|------|--------|
| **Persistence** | ✗ | ✓ | ✓ | ✓ | ✗ |
| **Distributed** | ✓ | ✓ | ✓ | ✗ | ✗ |
| **Consistency** | Eventual | Strong | Strong | N/A | N/A |
| **Speed** | Very Fast | Fast | Very Fast | Medium | Fastest |
| **Use Case** | Caching | Coordination | General Purpose | Single Node | Development |
| **Memory Usage** | Medium | Low | Medium | Disk | High |
| **Complexity** | Low | Medium | Medium | Low | Minimal |

## Choosing the Right Backend

### Use **Memcached** when:
- You need **high-speed temporary storage**
- Data loss on restart is acceptable
- You want **simple distributed caching**
- Memory efficiency is important

### Use **etcd** when:
- You need **strong consistency guarantees**
- **Persistent storage** is required
- You're running **distributed workflows**
- You need **watch/notification capabilities**
- **Production reliability** is critical

### Use **Redis** when:
- You need both **speed and persistence**
- You want **rich data structures**
- **Pub/sub capabilities** are needed
- You need **advanced features** (TTL, transactions, etc.)

### Use **File** when:
- You have a **single-node deployment**
- You want **simple persistence**
- You need **human-readable storage** (JSON)
- You don't need **high concurrency**

### Use **Memory** when:
- You're in **development/testing**
- **Maximum speed** is needed
- Data loss is acceptable
- You have a **simple workflow**

## Configuration Examples

### .env File

```bash
# Memcached configuration
OFX_REGISTRY_BACKEND=memcached
OFX_REGISTRY_MEMCACHED_HOST=cache.example.com
OFX_REGISTRY_MEMCACHED_PORT=11211
OFX_REGISTRY_MEMCACHED_PREFIX=ofx:prod:

# etcd configuration
OFX_REGISTRY_BACKEND=etcd
OFX_REGISTRY_ETCD_HOST=etcd.example.com
OFX_REGISTRY_ETCD_PORT=2379
OFX_REGISTRY_ETCD_PREFIX=/ofx/workflows/
```

### Using from Settings

```python
from ofx.runner.core import create_registry_from_settings

# Automatically uses environment variables or .env file
registry = create_registry_from_settings()
```

## Troubleshooting

### Memcached Connection Issues

```python
# Test Memcached connectivity
import asyncio
import aiomcache

async def test_memcached():
    client = aiomcache.Client("localhost", 11211)
    await client.set(b"test", b"value")
    value = await client.get(b"test")
    print(f"Memcached OK: {value}")
    await client.close()

asyncio.run(test_memcached())
```

### etcd Connection Issues

```python
# Test etcd connectivity
import etcd3

def test_etcd():
    client = etcd3.client(host='localhost', port=2379)
    client.put('/test', 'value')
    value, _ = client.get('/test')
    print(f"etcd OK: {value}")
    client.close()

test_etcd()
```

### Common Issues

1. **Connection Refused**: Ensure the server is running
   ```bash
   # Check Memcached
   telnet localhost 11211
   
   # Check etcd
   curl http://localhost:2379/version
   ```

2. **Import Errors**: Install the optional dependencies
   ```bash
   pip install ofx[memcached]
   pip install ofx[etcd]
   ```

3. **Permission Errors**: Ensure network access to the servers
   ```bash
   # Test network connectivity
   nc -zv localhost 11211  # Memcached
   nc -zv localhost 2379   # etcd
   ```

## Performance Tips

### Memcached
- Use connection pooling (`pool_size`, `pool_minsize`)
- Set appropriate key prefixes to avoid collisions
- Monitor memory usage and set appropriate limits
- Use consistent hashing for distributed deployments

### etcd
- Use batch operations when possible
- Set appropriate timeouts for network latency
- Use prefix-based queries efficiently
- Monitor cluster health in production
- Use TLS for secure communication

## Advanced Usage

### Custom Prefix for Multi-Tenancy

```python
# Separate registries for different environments
prod_registry = create_job_registry(
    "memcached",
    prefix="ofx:prod:job:"
)

dev_registry = create_job_registry(
    "memcached",
    prefix="ofx:dev:job:"
)
```

### High Availability etcd Cluster

```python
# Connect to etcd cluster with multiple endpoints
registry = create_job_registry(
    "etcd",
    host="etcd1.example.com,etcd2.example.com,etcd3.example.com",
    port=2379,
    timeout=10
)
```

## Migration Guide

### From Memory to Memcached

```python
# 1. Export data from memory registry
old_data = await memory_registry.get_all()

# 2. Create new Memcached registry
new_registry = create_job_registry("memcached")

# 3. Import data
for key, value in old_data.items():
    await new_registry.set(key, value)
```

### From Memcached to etcd

```python
# 1. Export from Memcached
memcached_data = await memcached_registry.get_all()

# 2. Create etcd registry
etcd_registry = create_job_registry("etcd")

# 3. Import to etcd (with persistence)
for key, value in memcached_data.items():
    await etcd_registry.set(key, value)
```

## See Also

- [Job Registry Architecture](job-registry-architecture.md)
- [Job Registry Quick Reference](job-registry-quick-ref.md)
- [Job Registry Main Documentation](job-registry.md)
