# Core Reference

Documentation for the core internals of OFX, including runners, models, and configuration.

## Runner

## Modules

Modules are the execution unit behind every step: `module:` names a builtin,
a workflow-local file, or a remote GitHub module. The implementation lives in
`ofx.modules`.

| Component | Responsibility |
|-----------|----------------|
| `ofx.modules.ModuleRegistry` | Parses a `module:` reference (`ofx.modules.refs.parse_module_ref`) and resolves it to a `ModuleSpec` |
| `ofx.modules.ModuleRunner` | Executes a resolved spec for a step: receives a `ModuleInvocation` and a `RunContext`, records outputs |
| `ofx.modules.base` | `ModuleContext` (the `ctx` handed to Python/UDF modules), `ModuleSpec`, `ModuleResult` |
| `ofx.modules.remote` | Remote module resolution: clone/cache/update of `<owner>.<repo>.<module>` refs and manifest validation |
| `ofx.modules.builtins` | The builtin modules: `shell`, `python`, `merge_lists`, `normalize_targets`, `classify_targets` |

`ofx.modules.base.DEFAULT_MODULE_FUNCTION` is the default entry-point name when a reference
omits `::<func>`.

See [Steps → Modules](../guide/jobs-steps/steps.md#modules) for the reference grammar
and worked examples.
