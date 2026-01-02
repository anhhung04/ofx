# secret

Manage secrets and credentials.

## Usage

```bash
ofx secret <subcommand> [options]
```

## Subcommands

### add

Add a new secret.

```bash
ofx secret add <name> [--value <value>] [--file <file>]
```

### list

List all secrets.

```bash
ofx secret list [--show-values]
```

### get

Get a specific secret value.

```bash
ofx secret get <name>
```

### delete

Delete a secret.

```bash
ofx secret delete <name>
```

### import

Import secrets from file.

```bash
ofx secret import <file>
```

### export

Export secrets to file.

```bash
ofx secret export [--output <file>]
```

## Description

The `secret` command provides secure storage and management of sensitive data like API keys, passwords, and tokens. Secrets are encrypted at rest and can be used in workflows.

## Examples

### Add a secret interactively

```bash
ofx secret add SHODAN_API_KEY
# Will prompt for value
```

### Add secret from command line

```bash
ofx secret add API_TOKEN --value "secret_value_here"
```

### Add secret from file

```bash
ofx secret add SSH_KEY --file ~/.ssh/id_rsa
```

### List secrets (values hidden)

```bash
ofx secret list
```

### Show secret values

```bash
ofx secret list --show-values
```

### Get specific secret

```bash
ofx secret get SHODAN_API_KEY
```

### Delete a secret

```bash
ofx secret delete OLD_TOKEN
```

### Import from JSON file

```bash
ofx secret import secrets.json
```

### Export secrets

```bash
ofx secret export --output backup.json
```

## Secret Storage

Secrets are stored encrypted in:

```
~/.local/share/ofx/secrets.enc
```

Encryption uses a master key derived from your system credentials.

## Using Secrets in Workflows

Reference secrets in workflows:

```yaml
name: api-scan
jobs:
  scan:
    steps:
      - name: Scan with API
        run: |
          curl -H "X-API-Key: ${{ secrets.SHODAN_API_KEY }}" \
            https://api.shodan.io/search
```

## Import/Export Format

JSON format:

```json
{
  "secrets": {
    "API_KEY": "value1",
    "PASSWORD": "value2"
  },
  "metadata": {
    "exported_at": "2024-01-01T00:00:00Z"
  }
}
```

## Security Features

- **Encryption at rest**: AES-256 encryption
- **Secure input**: Values hidden during interactive input
- **Access control**: Per-user secret stores
- **Audit logging**: Secret access logged
- **Auto-masking**: Values masked in logs

## See Also

- [Secrets Guide](../../guide/secrets-inputs/secrets.md)
- [Inputs](../../guide/secrets-inputs/inputs.md)
