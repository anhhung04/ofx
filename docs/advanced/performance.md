# Performance Optimization

OFX includes several performance optimizations to ensure fast execution and efficient resource usage.

## Template Resolution Caching

### Problem

Template resolution was creating new dictionaries and compiling Jinja2 templates on every call.

### Solution

- **SUPPORT_FUNCS caching**: Dictionary created once, reused across all instances
- **Template compilation caching**: Compiled Template objects stored and reused
- **Cache size limiting**: Maximum 1,000 templates prevents memory bloat

### Performance Impact

```
Template resolution: 0.013ms per call
5,000 resolutions: 0.065s
```

## Lazy Connector Discovery

### Problem

Connector discovery performed filesystem scanning at module import time.

### Solution

- Discovery deferred until first `get_connector()` call
- No I/O overhead for unused APIs

### Performance Impact

```
Module import (lazy): 0.002s
Module import (eager): 0.008s
Connector discovery: 0.006s (only when needed)
```

## Benchmarking

Run the included benchmark:

```bash
python benchmark_perf.py
```

### Sample Output

```
🚀 OFX Performance Benchmark

============================================================
✓ Template resolution (1000 iterations × 5 templates): 0.065s
  Average per template: 0.013ms
============================================================
✓ Module import (lazy discovery): 0.002s
✓ Connector discovery: 0.006s
============================================================
```

## Best Practices

### For Workflow Authors

1. **Reuse templates**: Identical template strings benefit from compilation caching
2. **Keep workflows concise**: Fewer unique templates = better cache hit rate
3. **Use variables**: `${{ variable }}` templates are cached and fast

### For Developers

1. **Don't disable caching**: Performance gains are significant
2. **Monitor cache size**: Consider if 1,000 template limit is appropriate
3. **Profile before optimizing**: Use benchmark to measure changes

## Memory Usage

### Template Cache

- **Maximum size**: 1,000 compiled templates
- **Auto-clear**: Cache cleared when limit reached
- **Typical usage**: 10-50 unique templates per workflow
- **Memory per template**: ~2-5KB

### SUPPORT_FUNCS Cache

- **Size**: ~15 function references
- **Memory**: <1KB
- **Lifetime**: Class-level (shared across instances)

## Profiling Workflows

### Enable Debug Logging

```python
import logging
logging.getLogger('ofx').setLevel(logging.DEBUG)
```

### Time a Workflow

```bash
time ofx flow run workflow.yml
```

### Python Profiler

```bash
python -m cProfile -o profile.stats -m ofx.commands.flow.run workflow.yml
python -m pstats profile.stats
```

## Future Optimizations

- [ ] Cache statistics/monitoring
- [ ] JIT compilation for frequent templates
- [ ] Persistent cache across runs
- [ ] Incremental connector discovery
- [ ] Command execution pooling

## See Also

- [PERFORMANCE.md](https://github.com/anhhung04/ofx/blob/main/PERFORMANCE.md) - Detailed performance documentation
- [API Overview](../api/overview.md) - Red teaming APIs
