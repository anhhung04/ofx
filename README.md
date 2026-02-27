# Offensive Flow Executor (OFX)

Workflow runner for red-team style automation: YAML workflows, parallel jobs, templating, and built-in APIs for recon, exploitation, and post-exploitation.

- **Docs:** https://anhhung04.github.io/ofx/

## Virtualenv / uv import tip

If you install from source in a venv or with `uv` and want `python` to import `ofx` without editable installs, drop a `.pth` file pointing at the repo `src` directory:

```bash
python3 - <<'PY'
import sysconfig, pathlib, subprocess, os
uv_tool_dir = subprocess.check_output(["uv", "tool", "dir"]).strip().decode()
tool_python_path = pathlib.Path(uv_tool_dir) / "ofx" / "bin" / "python"
tool_module_path = subprocess.check_output([tool_python_path, "-c", "import ofx; print(ofx.__path__[0])"]).strip().decode()
print(f"OFX module path: {tool_module_path}")
tool_modules_dir = pathlib.Path(tool_module_path).parent
tool_modules_dir.mkdir(parents=True, exist_ok=True)
try:
  pth_dir = pathlib.Path(sysconfig.get_paths()["purelib"])
  pth_dir.mkdir(parents=True, exist_ok=True)
  (pth_dir / "ofx.pth").write_text(str(tool_modules_dir))
except Exception as e:
  print(f"Error writing .pth file: {e}")
  print(f"Write to {os.environ['HOME']}/.local/lib/python{sysconfig.get_python_version()}/site-packages/ofx.pth with content: {tool_modules_dir}")
else:
  print(f"Wrote .pth file to {pth_dir/'ofx.pth'} pointing to {tool_modules_dir}")
print(f"Wrote {pth_dir/'ofx.pth'}")
PY
```

Run this from the repository root inside the target environment so `src/ofx` is added to `sys.path`.

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
