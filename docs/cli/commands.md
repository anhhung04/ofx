# CLI Commands Reference

This page provides a high-level command map. Detailed flags and examples are documented in each command page under `cli/commands/`.

## Top-level commands

| Command | Purpose |
|---|---|
| `flow` (`x`) | Run and manage workflows |
| `cloud` | Manage cloud profiles, instances, images, fleets |
| `session` | Manage detached local/cloud sessions |
| `project` (`p`) | Manage projects and project context |
| `secret` | Manage encrypted secrets |
| `api` | Inspect OFX API modules/functions |
| `docs` | Documentation helpers |
| `doctor` | Reliability scorecards and diagnostics |
| `ai` | AI-assisted workflow and analysis operations |

## Common usage

```bash
ofx <command> <subcommand> [options]
```

Global options are available via help:

```bash
ofx --help
ofx <command> --help
```

## Most-used commands

```bash
# validate + run
afx(){ ofx flow validate "$1" && ofx flow run "$1"; }
afx workflow.yml

# run with input
ofx flow run workflow.yml --input target=example.com

# run for project context
ofx flow run workflow.yml --project my-engagement

# list sessions
ofx session list

# manage secrets
ofx secret list
ofx secret set API_KEY
```

## Detailed command docs

- [CLI command index](commands/index.md)
- [Flow run](commands/run.md)
- [Flow validate](commands/validate.md)
- [Flow visualize](commands/visualize.md)
- [Flow schema](commands/schema.md)
- [Flow collections](commands/collection.md)
- [Project commands](commands/project.md)
- [Secret commands](commands/secret.md)
- [API command](commands/api.md)
- [Doctor](commands/doctor.md)
- [Docs server](commands/docs-serve.md)

## Troubleshooting

- If a command fails unexpectedly, run with `OFX_DEBUG=1`.
- Use `ofx doctor fleet` to validate fleet/cloud run readiness.
