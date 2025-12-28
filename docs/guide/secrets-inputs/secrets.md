# Secrets

Secrets are sensitive values (API keys, passwords, tokens) used in OFX workflows. OFX provides secure storage, encryption, and injection of secrets into jobs and steps.

---

## How to Set Secrets
```bash
ofx secret set API_KEY=abcdef12345
```
Or interactively:
```bash
ofx secret set
# Prompts for key and value (input hidden)
```

---

## Using Secrets in Workflows
Reference secrets in YAML using the `secrets.` namespace:
```yaml
run: curl -H "Authorization: Bearer {{ secrets.API_KEY }}" https://api.example.com
```

---

## Secret Storage
- Secrets are stored encrypted (if enabled) in the project directory
- Use `ofx secret list` to view available secrets
- Use `ofx secret delete <key>` to remove a secret

---

## Best Practices
- Never hardcode secrets in workflow files
- Use environment variables or secret storage for sensitive data
- Rotate secrets regularly

---

## See Also
- [Inputs](inputs.md)
- [Secret CLI Reference](../../cli/commands.md#secret)