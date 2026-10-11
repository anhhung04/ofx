# flow modules

Manage namespaced **remote modules** — reusable Python modules published in GitHub repos and referenced from workflows as `<owner>.<repo>.<module>[@<ref>][::<func>]`.

## Usage

```bash
ofx flow modules <subcommand> [options]
```

Repos are cached under `~/.ofx/modules/<owner>/<repo>[@<ref>]` (override the root with the `OFX_MODULES_DIR` environment variable). Unpinned clones are reused as-is; pinned refs are immutable (one clone per ref).

---

## Subcommands

### list

List builtin modules, cached remote modules, and workflow-local modules.

```bash
ofx flow modules list [options]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--local / --no-local` | Include workflow-local `modules/*.py` from the cwd (default: on) |

**Example output:**

```
Modules (cache: /home/dev/.ofx/modules)
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Type    ┃ Name                      ┃ Location                       ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ builtin │ python                    │ built-in                       │
│ builtin │ shell                     │ built-in                       │
│ remote  │ anhhung04.ofx-modules     │ ~/.ofx/modules/anhhung04/...   │
│ local   │ port_scan                 │ ./modules/port_scan.py         │
└─────────┴───────────────────────────┴────────────────────────────────┘
```

---

### add

Pre-clone a remote module repo into the local cache (without running it).

```bash
ofx flow modules add <owner>.<repo>[@<ref>]
```

**Arguments:**

- `owner.repo[@ref]` (required) — GitHub repo to clone; `@ref` pins a tag/branch/commit.

**Options:**

| Option | Description |
|--------|-------------|
| `--verify-manifest / --no-verify-manifest` | Validate `ofx-modules.yml` right after cloning (default: on) |

**Examples:**

```bash
ofx flow modules add anhhung04.ofx-modules
ofx flow modules add anhhung04.ofx-modules@v1.2.0
```

---

### update

Pull the latest changes for **unpinned** cached clones.

```bash
ofx flow modules update [owner.repo]
```

**Arguments:**

- `owner.repo` (optional) — Clone to update. Omit to update every unpinned clone.

Pinned clones (`@<ref>`) are immutable and skipped — remove and re-add with the new ref instead.

```bash
ofx flow modules update
ofx flow modules update anhhung04.ofx-modules
```

---

### remove

Delete a cached module clone.

```bash
ofx flow modules remove <owner>.<repo>[@<ref>]
```

**Arguments:**

- `owner.repo[@ref]` (required) — Cached clone to delete.

Refuses to delete anything outside `MODULES_DIR`.

```bash
ofx flow modules remove anhhung04.ofx-modules
ofx flow modules remove anhhung04.ofx-modules@v1.2.0
```

---

### info

Resolve a remote module spec and show its entry file and function.

```bash
ofx flow modules info <owner>.<repo>.<module>[@<ref>]
```

**Arguments:**

- `owner.repo.module[@ref]` (required) — Module spec to resolve (clones the repo if not cached).

```bash
ofx flow modules info anhhung04.ofx-modules.parse_nmap
```

---

!!! warning "Remote modules are arbitrary code"
    Referencing a remote module downloads and executes Python from that repo. OFX does not sandbox module code — only use repos you trust, and prefer pinning `@<tag>`.

## See Also

- [Steps — Modules](../../guide/jobs-steps/steps.md#modules) — Reference forms, publishing layout, and the module contract
- [flow collection](collection.md) — Install whole workflow collections
