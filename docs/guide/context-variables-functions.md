# Built-in Variables & Functions

When writing and executing workflows, OFX provides a rich set of built-in variables, Jinja template functions, and shell helpers. These are automatically available during the evaluation of template strings (like `{{ ... }}`) and in the execution environment of your shell scripts.

## Core Variables

The core variables give you direct access to the configuration state, dependencies, user inputs, and output streams of your workflows. 

### Inputs & Secrets
Inputs and Secrets represent values explicitly passed into a workflow dynamically by the user at runtime. These context dictionaries hold those overrides cleanly distinct from environment definitions:

- `{{ inputs.<key> }}`: Retrieve the given user runtime input value passed via configuration, `.yaml` definitions, or the `--input` flag through the CLI.
- `{{ secrets.<key> }}`: Retrieve the decrypted stored secret matching the given key.

### Jobs (Dependencies / Needs) 
The `jobs` template dictionary is automatically populated internally with outputs from any jobs specified in the current job's `needs` array! Because steps and operations might depend entirely on intermediate execution parsing logic, jobs write output variables to the job registry which OFX automatically surfaces securely into any dependent subsequent blocks:

- `{{ jobs.<job_id>.outputs.<output_key> }}`: Pull the extracted state mapping parsed out of an earlier workflow block via the given job key. Note that you MUST list `job_id` under your current job `needs` array property for these values to be dependably synchronized on time!

### Steps
You can retrieve the extracted values returned by **preceding steps within the same job** via the local runtime array index list mapped securely to `steps`.

- `{{ steps[integer_index].outputs.<output_key> }}`

### Internal System Variables
These properties represent runtime environmental context specific to your local host execution space:

| Variable | Type | Description |
|---|---|---|
| `is_windows` | `bool` | `True` if the runner is executing on Windows. |
| `platform` | `str` | Either `"windows"` or `"unix"`. |
| `sudo` | `str` | Output of `_get_sudo()`. Equivalent to `"sudo "` if the user possesses sudo privileges and isn't root, else `""`. |
| `tools_dir` | `str` | Absolute path to the OFX configured tools storage directory. |
| `tools_bin_dir` | `str` | Absolute path to the OFX tools binaries directory. |
| `temp_dir` | `str` | Absolute path to the OFX temporary directory. |
| `python` | `str` | Path to the current python executable running OFX. |

*Example usage:*
```yaml
run: echo "Given target: {{ inputs.target }} against execution workspace {{ tools_dir }} on {{ platform }}"
```

---

## Jinja Template Functions (Filters / Helpers)

You can use these helper functions inside any template expression (`{{ ... }}`).

### File Utilities
| Function | Description |
|---|---|
| `file_read(path)` | Reads file contents as a string. |
| `file_write(path, content)` | Writes contents to a file natively. |
| `file_append(path, content)` | Appends contents to a file. |
| `file_lines(path)` | Reads a file and returns a list of lines. |
| `file_exists(path)` | Returns `True` if the path exists. |
| `is_file(path)` | Returns `True` if the path is a file. |
| `is_dir(path)` | Returns `True` if the path is a directory. |

### Path Utilities
| Function | Description |
|---|---|
| `join_path(*parts)` | Safely joins path components. |
| `basename(path)` | Returns the base filename. |
| `dirname(path)` | Returns the directory name of the path. |
| `glob(pattern, directory=".")` | Returns a list of paths matching the glob pattern. |
| `cwd()` | Returns the current working directory string. |
| `home()` | Returns the home directory string. |

### Encodings and Hashes
| Function | Description |
|---|---|
| `b64encode(s)`, `b64decode(s)` | Base64 encode/decode strings. |
| `url_encode(s)`, `url_decode(s)` | URL encode/decode strings. |
| `hex_encode(s)`, `hex_decode(s)` | Hexadecimal encode/decode strings. |
| `md5(s)`, `sha1(s)`, `sha256(s)` | Return checksum hash for a string. |

### Random Generators
| Function | Description |
|---|---|
| `random_string(length=8, charset="alphanumeric")` | Generates a random string. Supported character sets: `"alpha"`, `"numeric"`, `"hex"`, `"alphanumeric"`. |
| `random_int(min_val=0, max_val=100)` | Generates a random integer securely. |
| `random_port(start=1024, end=65535)` | Generates a random valid unprivileged port. |
| `uuid()` | Generates a random UUID (version 4). |
| `token(n=32)` | Generates a secure URL-safe base64 token. |

### Network & Time
| Function | Description |
|---|---|
| `local_ip()` | Attempts to resolve the machine's local IP address, returning `127.0.0.1` as a fallback. |
| `is_port_open(host, port, timeout=1.0)` | Probes if a remote port is open. |
| `now(fmt="%Y-%m-%d %H:%M:%S")` | Yields the formatted current datetime. |
| `timestamp()` | Yields the current epoch UNIX timestamp. |

### Data Parsing
| Function | Description |
|---|---|
| `to_json(obj)` | Serializes a Python object into a JSON string. |
| `from_json(s)` | Parses a JSON string back into a Python object/dict. |

### Regex Utilities
| Function | Description |
|---|---|
| `regex_match(pattern, s)` | Returns `True` if `s` is matched entirely by `pattern`. |
| `regex_search(pattern, s)` | Returns `True` if `pattern` is found in `s`. |
| `regex_findall(pattern, s)` | Returns all occurrences of `pattern` in `s`. |
| `regex_sub(pattern, repl, s)` | Returns a string substituting `pattern` with `repl` inside `s`. |

### Typed Output Helpers

Filter task typed outputs by type. These accept a list of typed output dicts and return only items matching the specified type:

| Function | Filters for `_type` |
|---|---|
| `ports(items)` | `port` |
| `urls(items)` | `url` |
| `vulns(items)` | `vulnerability` |
| `subdomains(items)` | `subdomain` |
| `ips(items)` | `ip` |
| `tags(items)` | `tag` |
| `records(items)` | `record` |
| `domains(items)` | `domain` |
| `users(items)` | `user_account` |
| `certs(items)` | `certificate` |
| `exploits(items)` | `exploit` |
| `of_type(items, "type_name")` | Any custom type |

### ETL & Data Transformation Helpers

These functions transform lists of data and are available both as template functions and as Jinja2 pipe filters (`|`). They pair naturally with [pipe steps](jobs-steps/steps.md#pipe-steps) for declarative data processing.

| Function / Filter | Description |
|---|---|
| `pluck(items, key)` | Extract a single attribute from each item. `{{ items \| pluck("host") }}` |
| `to_lines(items)` | Join items with newlines. `{{ items \| to_lines }}` |
| `to_csv(items, fields, separator)` | Format dicts as CSV rows. `{{ items \| to_csv("host,port") }}` |
| `to_jsonl(items)` | Format items as JSON Lines (one JSON object per line). |
| `sort_by(items, key, reverse=False)` | Sort dicts by a key. `{{ items \| sort_by("port") }}` |
| `unique_by(items, key)` | Deduplicate dicts by a key. `{{ items \| unique_by("host") }}` |
| `where(items, key, value)` | Filter dicts where `key == value`. `{{ items \| where("status", "open") }}` |
| `where_not(items, key, value)` | Filter dicts where `key != value`. |
| `first(items, n=1)` | Return the first N items. `{{ items \| first(5) }}` |
| `last(items, n=1)` | Return the last N items. |
| `group_by(items, key)` | Group items by key, returns `{key_value: [items...]}`. |
| `flatten(items)` | Flatten nested lists one level. |
| `count_by(items, key)` | Count occurrences by key value, returns `{value: count}`. |

**Example — chaining filters:**
```yaml
run: |
  echo "Top 10 unique hosts:"
  echo "{{ steps['scan'].outputs.typed_outputs | ports | pluck('host') | unique_by('host') | first(10) | to_lines }}"
```

### Findings Export

| Function | Description |
|---|---|
| `export_typed_outputs(project_path, items, prefix)` | Export typed output dicts to organized project directories (master files + per-target subdirectories). |

### ASM Integration

These functions integrate with the OFX Attack Surface Management module. They degrade gracefully (returning empty results) when ASM is not configured:

| Function | Description |
|---|---|
| `asm_targets(scope, effective, target_type)` | Retrieve target values from an ASM scope. Returns a list of strings (domains, IPs, etc.). |
| `asm_push(items, scope, source)` | Push typed output dicts to an ASM scope. Returns the count of imported assets. |
| `asm_scopes()` | List available ASM scopes as dicts with `id`, `name`, `scope_type`, and `group` fields. |

---

## Shell Helper Functions

The following shell functions are automatically prepended and exported to your environment when using the `run` step. They work transparently across **Bash** and **PowerShell**:

### Installation Helpers
These simplify setting up tools quickly without dealing with raw package managers in multiple OS environments:

- `fapt [packages...]`: Fast APT install (auto-updates `apt` if cache is empty, asks for `sudo` only when running unprivileged). *Bash only*.
- `uv_install [packages...]`: Installs Python tools utilizing the `uv` toolchain.
- `go_install [package]`: Wraps `GO111MODULE=on go install ...@latest`. Places binaries properly in `TOOLS_BIN_DIR`.
- `cargo_install [packages...]`: Compiles internal Rust tools with `cargo` and saves them locally.
- `npm_install [packages...]`: Installs tools using NPM.
- `pip_install [packages...]`: Upgrades and installs PyPI packages within the current embedded runtime context.
- `static_install [url] [name]`: Quickly downloads a static binary using `curl` (Linux) or `Invoke-WebRequest` (Windows) straight into configured `$TOOLS_BIN_DIR` and makes it executable.

### Channel Communication
OFX features native inter-process/inter-job communication channels utilizing filesystem file-locking for cross-process synchronization.

- `ch_publish <channel> <data>`: Publishes arbitrary string data directly to a channel.
- `ch_get <channel>`: Reads the current value of the channel.
- `ch_subscribe <channel> [interval]`: Automatically tracks continuous channel updates over time.
- `ch_wait_for <channel> <expected_value> [timeout] [interval]`: Hangs the workflow shell process cleanly until a specified channel equals `expected_value`. Useful to implement inter-process waits!

---

## Auto-Populated Context Variables

Depending on the job or workflow features being used, OFX auto-populates specific context variables for your templates and environment variables for your shell scripts. For full details on how these variables behave in Remote VPS vs Local contexts natively, see [Cloud Variables](cloud/variables.md).

### Matrix Context
When using a `strategy.matrix`, the current combination is available in the `matrix` variable scope:
- `{{ matrix.<key> }}`: The specific value for the given matrix key in the current job instance.

### Fleet Context
When using fleet distribution (`strategy.fleet`), the following are injected locally:
- `{{ fleet.fleet_input_file }}`: The local temporary file containing the chunk of targets for the current instance.
- `{{ fleet.fleet_index }}`: The current fleet chunk index (0-based).
- `{{ fleet.fleet_target_count }}`: The number of targets in this specific chunk.
- `{{ fleet.fleet_total }}`: The total number of fleet chunks generated.

*Note for Cloud Fleet Jobs:* When fleet jobs are executed on remote cloud instances, these variables are explicitly exported to the environment with a `REMOTE_` prefix, and `REMOTE_FLEET_INPUT_FILE` correctly points to the remote uploaded path instead of the local temp file loop:
- `$REMOTE_FLEET_INPUT_FILE`: The remote filesystem path to the uploaded chunk file.
- `$REMOTE_FLEET_INDEX`: The index of the fleet chunk.

### Cloud Context
When a job provisions a cloud instance via the `cloud:` property, OFX stores metadata in the job registry (making it accessible to subsequent jobs that depend on it via the `needs` parameter):
- `{{ jobs.<job_id>.cloud_instance.ip }}`: The public IP address of the provisioned VPS.
- `{{ jobs.<job_id>.cloud_instance.instance_id }}`: The provider's unique instance identifier.
- `{{ jobs.<job_id>.cloud_instance.provider }}`: The cloud provider used.

### Session Context
For detached sessions submitted via the `ofx session` CLI, the session architecture primarily manages state implicitly. Operations run as self-contained background workers or detached cloud jobs, resolving `matrix`, `fleet`, and standard secrets securely via standard templating rules documented above. State markers tracking provisioning, uploading, and encrypting statuses run safely abstracted from regular job contexts. For a deep dive into session lifecycles, view the [Detached Sessions](cloud-sessions.md) reference.
