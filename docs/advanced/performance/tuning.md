# Performance Tuning

Optimize your OFX workflows for speed, efficiency, and resource usage. This page covers best practices and configuration tips for high-performance automation.

---

## Tips for Faster Workflows
- **Minimize job dependencies:** Only use `needs:` where necessary to maximize parallelism
- **Batch small steps:** Combine related commands into a single step to reduce overhead
- **Use efficient tools:** Prefer fast, command-line tools for scanning and exploitation
- **Limit output:** Avoid excessive logging or large outputs in steps

---

## Resource Management
- **CPU:** Limit the number of parallel jobs if CPU-bound
- **Memory:** Monitor memory usage for large data processing steps
- **Disk:** Clean up temporary files and artifacts after jobs complete

---

## Example: Parallel Jobs
```yaml
jobs:
	scan1:
		steps:
			- run: nmap 10.0.0.1
	scan2:
		steps:
			- run: nmap 10.0.0.2
	scan3:
		steps:
			- run: nmap 10.0.0.3
```
All three jobs run in parallel, speeding up the workflow.

---

## Tuning Timeouts
- Set `timeout:` on long-running steps to avoid hangs
- Increase timeouts for slow network or large scans

---

## Monitoring
- Use `--debug` to profile workflow execution
- Integrate with system monitoring tools for large-scale runs

---

## See Also
- [Performance Troubleshooting](troubleshooting.md)
- [Workflow Stages](../../guide/workflows/stages.md)