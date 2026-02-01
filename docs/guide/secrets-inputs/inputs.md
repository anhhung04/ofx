# Inputs

Inputs are variables provided to OFX workflows at runtime. Use inputs to parameterize workflows, pass targets, credentials, or other dynamic values.

---

## How to Provide Inputs
```bash
ofx flow run workflow.yml --input target=example.com --input env=prod
```

---

## Using Inputs in YAML
Reference inputs in workflow files using the `inputs.` namespace:
```yaml
run: echo "Target is {{ inputs.target }}"
```

---

## Default Values
You can set default values for inputs in your workflow YAML:
```yaml
inputs:
	target: "localhost"
	env: "dev"
```

---

## Best Practices
- Validate required inputs at the start of your workflow
- Use descriptive input names
- Document expected inputs in your project README

---

## See Also
- [Secrets](secrets.md)
- [Inputs CLI Reference](../../cli/commands/run.md)