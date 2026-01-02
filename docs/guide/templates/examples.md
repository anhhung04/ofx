# Template Examples

This page provides practical examples of using Jinja2 templates in OFX workflows for dynamic configuration, variable substitution, and output formatting.

---

## Basic Variable Substitution
```yaml
run: echo "Target is ${{ inputs.target }}"
```

---

## Using Step Outputs
```yaml
steps:
	- name: Scan
		run: nmap ${{ inputs.target }}
		outputs:
			open_ports: "${{ step.stdout_lines }}"
	- name: Print Ports
		run: echo "Ports: {{ steps.0.outputs.open_ports }}"
```

---

## Looping Over Values
```yaml
run: |
	{% for port in jobs.scan.outputs.open_ports %}
	echo "Port: {{ port }}"
	{% endfor %}
```

---

## Conditional Logic
```yaml
run: |
	{% if inputs.env == 'prod' %}
	echo "Production environment"
	{% else %}
	echo "Development environment"
	{% endif %}
```

---

## Filters and Formatting
```yaml
run: echo "Upper: ${{ inputs.name | upper }}"
```

---

## See Also
- [Jinja Template Reference](jinja.md)