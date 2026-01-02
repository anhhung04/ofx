# Init Command

Initializes a new OFX project or workflow directory. This command scaffolds the required folder structure, creates a sample workflow, and optionally sets up Git integration and secret storage.

---

## Usage
```bash
ofx project init [OPTIONS]
```

---

## Options
- `--name <project_name>`: Specify the project name (default: current directory name)
- `--git`: Initialize a Git repository
- `--remote <url>`: Set a remote Git URL
- `--encrypt`: Enable secret encryption for the project

---

## Example: Basic Project Initialization
```bash
ofx project init --name my-redteam-project
```

**Result:**
- Creates `my-redteam-project/` with `workflows/`, `secrets/`, and sample files

---

## Example: With Git and Encryption
```bash
ofx project init --git --remote https://github.com/user/ofx-demo.git --encrypt
```

**Result:**
- Initializes Git, sets remote, and enables encrypted secret storage

---

## After Initialization
- Add workflows to the `workflows/` directory
- Store secrets in the `secrets/` directory (encrypted if enabled)
- Use `ofx flow run <workflow>` to execute workflows

---

## See Also
- [Project Management](../../guide/workflows/index.md)
- [Secret Management](../../guide/secrets-inputs/index.md)

Initializes a new OFX project or workflow directory. This command scaffolds the required folder structure, creates a sample workflow, and optionally sets up Git integration and secret storage.

---

## Usage
```bash
ofx project init [OPTIONS]
```

---

## Options
- `--name <project_name>`: Specify the project name (default: current directory name)
- `--git`: Initialize a Git repository
- `--remote <url>`: Set a remote Git URL
- `--encrypt`: Enable secret encryption for the project

---

## Example: Basic Project Initialization
```bash
ofx project init --name my-redteam-project
```

**Result:**
- Creates `my-redteam-project/` with `workflows/`, `secrets/`, and sample files

---

## Example: With Git and Encryption
```bash
ofx project init --git --remote https://github.com/user/ofx-demo.git --encrypt
```

**Result:**
- Initializes Git, sets remote, and enables encrypted secret storage

---

## After Initialization
- Add workflows to the `workflows/` directory
- Store secrets in the `secrets/` directory (encrypted if enabled)
- Use `ofx flow run <workflow>` to execute workflows

---

## See Also
- [Project Management](../../guide/workflows/index.md)
- [Secret Management](../../guide/secrets-inputs/index.md)