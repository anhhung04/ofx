# Jinja Templates

OFX uses the Jinja2 template engine for dynamic variable substitution, logic, and formatting in workflow YAML files.

---

## Basic Syntax
- `${{ variable }}`: Output the value of a variable
- `{% if ... %} ... {% endif %}`: Conditional logic
- `{% for ... %} ... {% endfor %}`: Loops

---

## Common Filters
- `| upper`, `| lower`: Change case
- `| replace('a', 'b')`: Replace text
- `| join(',')`: Join list into string
- `| length`: Get length of list or string

---

## Example: Using Inputs
```yaml
run: echo "Scanning target ${{ inputs.target | upper }}!"
```

---

## Example: Looping
```yaml
run: |
	#!/bin/bash
	{% for port in jobs.scan.outputs.open_ports %}
	echo "Port: ${{ port }}"
	{% endfor %}
```

---

## Example: Conditionals
```yaml
run: |
	#!/bin/bash
	{% if inputs.env == 'prod' %}
	echo "Production"
	{% else %}
	echo "Dev"
	{% endif %}
```

---

## Advanced: Custom Filters
You can define custom filters in Python steps and use them in templates.

---

## See Also
- [Template Examples](examples.md)