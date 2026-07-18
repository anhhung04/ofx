# Security Policy

## Threat Model

OFX (Offensive Flow Executor) is **offensive security tooling** designed for use
on authorized red-team engagements.  Its threat model considers:

1. **Untrusted workflow files** — OFX workflows (YAML) downloaded from collections
   or shared between operators may contain malicious template expressions or tool
   installer commands.  OFX mitigates this via:
   - Sandboxed Jinja2 template rendering (dunder access, `os`, `subprocess` blocked)
   - `yaml.safe_load` at every YAML parse site
   - Tool installer policy gate (`~/.ofx/tools-policy.yml`)

2. **Secret leakage** — Operator credentials, API keys, and tokens loaded via
   `ofx secret` must not leak into logs, registry files, or crash reports.  OFX
   applies a `SecretRedactFilter` on the root logger and redacts error previews.

3. **Registry integrity** — File-based registry uses atomic writes (`tmp + rename`)
   with mode `0o600`.  Redis-based registry uses key prefixes to namespace runs.

4. **Operator host isolation** — OFX does not sandbox the operator's filesystem.
   Workflows run with the operator's privileges.  This is by design: operators
   need access to local tools, SSH keys, and engagement data.

## What is NOT a vulnerability in OFX

- **Red-team capabilities working as designed** — webshell generators, shellcode
  connectors, post-exploitation runners, evasion helpers, and C2 integration are
  intentional.  Do not report their existence as a security issue.

- **Abuse against unauthorized targets** — OFX is a tool.  Misuse against systems
  you do not have authorization to test is a legal matter, not an OFX vulnerability.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.9.x  | ✅ Current |
| < 0.9  | ❌ EOL    |

## Reporting a Vulnerability

If you discover a security issue in the OFX **framework** (template sandbox bypass,
secret leakage, registry corruption, dependency vulnerability, etc.):

1. **Do NOT open a public issue.**
2. Email: security@example.com (replace with your actual address)
3. Include: affected version, reproduction steps, impact assessment.
4. You will receive an acknowledgment within 72 hours.

We follow coordinated disclosure and will credit reporters in the release notes
unless anonymity is requested.
