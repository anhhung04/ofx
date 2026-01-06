# Offensive Flow Executor (OFX)

Workflow runner for red-team style automation: YAML workflows, parallel jobs, lifecycle hooks, templating, and built-in APIs for recon, exploitation, and post-exploitation.

- **Docs:** https://anhhung04.github.io/ofx/

## Install (uv)

```bash
uv pip install --upgrade pip  # optional but recommended
uv pip install ofx
# or editable from source
uv pip install -e .
```

## Quick Start

Create a workflow and run it:

```bash
cat << EOF > hello.yml
name: hello-ofx
jobs:
  hello:
    steps:
      - run: echo "Hello, OFX!"
EOF

ofx flow run hello.yml
```

## Core Capabilities

- YAML workflows with job dependencies and parallel stages
- Lifecycle hooks on steps, plus retries/timeouts and conditional `run_if`
- Built-in APIs for recon/exploitation/post-exploitation tasks
- Jinja templating for inputs, envs, secrets, and commands
- Async-first engine with rich progress output

## Contributing

PRs welcome. Use semantic commit messages. See the docs for development setup.

## License

See `LICENSE` for details.
