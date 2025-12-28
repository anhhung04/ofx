# Performance Troubleshooting

This page helps you diagnose and resolve performance issues in OFX workflows, such as slow job execution, resource bottlenecks, and unexpected delays.

---

## Common Issues
- **Slow job execution:** Jobs take longer than expected to complete
- **Resource contention:** Multiple jobs compete for CPU, memory, or network
- **Long startup times:** Workflow initialization is slow
- **Timeouts:** Steps or jobs exceed their allowed time

---

## Troubleshooting Steps
1. **Enable Debug Logging:**
	- Run with `--debug` to see detailed timing and resource usage
	- Example: `ofx flow run workflow.yml --debug`

2. **Check Job Dependencies:**
	- Ensure jobs are not waiting unnecessarily due to misconfigured `needs:`

3. **Review Resource Usage:**
	- Monitor system CPU, memory, and disk during workflow execution
	- Use tools like `htop`, `iotop`, or `docker stats` if running in containers

4. **Optimize Parallelism:**
	- Group independent jobs to run in parallel
	- Avoid too many parallel jobs if system resources are limited

5. **Increase Timeouts:**
	- If steps are timing out, increase the `timeout:` value in your YAML

---

## Example: Debugging a Slow Workflow
```bash
ofx flow run workflows/large_scan.yml --debug
```
Look for stages or steps with unusually long durations.

---

## Best Practices
- Use job dependencies to control execution order
- Set appropriate timeouts for long-running steps
- Monitor system resources during large workflows

---

## See Also
- [Performance Tuning](tuning.md)
- [Workflow Stages](../../guide/workflows/stages.md)