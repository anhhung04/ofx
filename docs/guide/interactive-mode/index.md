# Interactive Mode (Overview)

OFX supports interactive mode for steps, allowing stdin/stdout passthrough for interactive commands like shells, REPLs, or tools that require user input.

- [Usage](usage.md)
- [Detection & Execution](detection.md)
- [Limitations](limitations.md)
- [Examples](examples.md)
- [Best Practices](best-practices.md)
- [Error Handling & Troubleshooting](error-handling.md)

Interactive mode is **automatically enabled** when:
1. A step has `interactive: true` flag set
2. The job containing the step is **alone in its execution stage** (no parallel jobs)

This prevents conflicts from multiple jobs trying to use stdin/stdout simultaneously.

See the subpages for details, YAML examples, and troubleshooting.