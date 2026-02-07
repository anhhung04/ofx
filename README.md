# Offensive Flow Executor (OFX)

Workflow runner for red-team style automation: YAML workflows, parallel jobs, templating, and built-in APIs for recon, exploitation, and post-exploitation.

Official distribution packages are Debian/Ubuntu .deb only. Use source installs for other environments.

- **Docs:** https://anhhung04.github.io/ofx/

## Install (Debian/Ubuntu)

```bash
# Download from releases
wget https://github.com/devhah4/ofx/releases/latest/download/ofx_0.4.0-1_all.deb

# Install
sudo dpkg -i ofx_0.4.0-1_all.deb
sudo apt-get install -f  # Fix any missing dependencies

# Verify
ofx --version
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
- Built-in APIs for recon/exploitation/post-exploitation tasks
- Jinja templating for inputs, envs, secrets, and commands
- Async-first engine with rich progress output

## Contributing

PRs welcome. Use semantic commit messages. See the docs for development setup.

## License

See `LICENSE` for details.
