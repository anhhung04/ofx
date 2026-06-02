# Jinja Templates

OFX uses Jinja2 for dynamic variable substitution, logic, and formatting in workflow YAML files. All string, number, and boolean fields are processed through the template engine before execution.

---

## Syntax

| Syntax | Purpose |
|--------|---------|
| `{{ expr }}` | Output the value of an expression |
| `{% if ... %} ... {% endif %}` | Conditional logic |
| `{% for ... %} ... {% endfor %}` | Loops |
| `{# comment #}` | Comments (stripped from output) |

---

## Variable Access

### Inputs and Secrets
```yaml
run: echo "Target: {{ inputs.target }}, Key: {{ secrets.API_KEY }}"
```

### Job and Step Outputs
```yaml
# Reference step outputs within the same job
run: echo "{{ steps['scan'].outputs.open_ports }}"

# Reference job outputs from a dependency
run: echo "{{ jobs.scan.outputs.result }}"
```

### Matrix Values
```yaml
run: echo "Scanning {{ matrix.target }} on port {{ matrix.port }}"
```

### Context Variables
```yaml
run: |
  echo "Run: {{ ctx.run_id }}"
  echo "Output: {{ ctx.output_path }}"
  echo "Platform: {{ platform }}"
```

---

## Filters

Filters transform values using the `|` pipe operator.

### Built-in Jinja2 Filters

| Filter | Example | Result |
|--------|---------|--------|
| `upper` | `{{ "hello" \| upper }}` | `HELLO` |
| `lower` | `{{ "HELLO" \| lower }}` | `hello` |
| `replace` | `{{ "foo-bar" \| replace("-", "_") }}` | `foo_bar` |
| `join` | `{{ [1,2,3] \| join(",") }}` | `1,2,3` |
| `length` | `{{ [1,2,3] \| length }}` | `3` |
| `default` | `{{ x \| default("none") }}` | `none` (if x is undefined) |
| `int` | `{{ "42" \| int }}` | `42` |
| `float` | `{{ "3.14" \| float }}` | `3.14` |
| `trim` | `{{ " hello " \| trim }}` | `hello` |
| `split` | `{{ "a,b,c" \| split(",") }}` | `['a', 'b', 'c']` |
| `first` | `{{ [1,2,3] \| first }}` | `1` |
| `last` | `{{ [1,2,3] \| last }}` | `3` |
| `sort` | `{{ [3,1,2] \| sort }}` | `[1, 2, 3]` |
| `unique` | `{{ [1,1,2] \| unique }}` | `[1, 2]` |
| `tojson` | `{{ data \| tojson }}` | JSON string |
| `selectattr` | `{{ items \| selectattr("port", "gt", 80) }}` | Filtered list |
| `map` | `{{ items \| map(attribute="host") }}` | Extracted attribute list |

### Chaining Filters

```yaml
# Get unique sorted ports as a comma-separated string
run: echo "{{ ports(steps['scan'].outputs.typed_outputs) | map(attribute='port') | sort | unique | join(',') }}"
```

---

## Conditionals

```yaml
run: |
  {% if inputs.mode == "stealth" %}
  echo "Running in stealth mode"
  nmap -sS -T2 {{ inputs.target }}
  {% elif inputs.mode == "aggressive" %}
  echo "Running aggressive scan"
  nmap -A -T4 {{ inputs.target }}
  {% else %}
  echo "Default scan"
  nmap {{ inputs.target }}
  {% endif %}
```

### Inline Conditionals (Ternary)

```yaml
run: nmap {{ "-sS" if inputs.stealth else "-sT" }} {{ inputs.target }}
```

---

## Loops

```yaml
run: |
  {% for host in jobs.discover.outputs.hosts.split(",") %}
  echo "Scanning {{ host }}"
  nmap -sV {{ host }}
  {% endfor %}
```

### Loop with Index

```yaml
run: |
  {% for port in [22, 80, 443, 8080] %}
  echo "Check {{ loop.index }}/{{ loop.length }}: port {{ port }}"
  {% endfor %}
```

---

## Typed Output Helpers

When working with task step outputs, use the built-in helper functions:

```yaml
# Filter by type
run: echo "{{ ports(steps['scan'].outputs.typed_outputs) | length }} ports found"

# Extract attributes
run: echo "{{ urls(steps['probe'].outputs.typed_outputs) | map(attribute='url') | join('\n') }}"

# Complex filtering
run: |
  {% set critical = vulns(steps['nuclei'].outputs.typed_outputs) | selectattr('severity', 'eq', 'critical') | list %}
  echo "Critical vulns: {{ critical | length }}"
```

Available helpers: `ports()`, `urls()`, `vulns()`, `subdomains()`, `ips()`, `tags()`, `records()`, `domains()`, `users()`, `certs()`, `exploits()`, `of_type(items, "type_name")`.

---

## ETL & Data Transformation Filters

OFX registers additional Jinja2 filters for transforming lists of data. These are especially useful with [pipe steps](../jobs-steps/steps.md#pipe-steps) and task outputs.

| Filter | Description |
|--------|-------------|
| `pluck("key")` | Extract a single field from each dict |
| `sort_by("key")` | Sort dicts by a field |
| `unique_by("key")` | Deduplicate dicts by a field |
| `where("key", "value")` | Keep dicts where field equals value |
| `where_not("key", "value")` | Exclude dicts where field equals value |
| `first(n)` | Take the first N items |
| `last(n)` | Take the last N items |
| `group_by("key")` | Group into `{value: [items]}` |
| `flatten` | Flatten nested lists one level |
| `count_by("key")` | Count occurrences: `{value: count}` |
| `to_lines` | Join items with newlines |
| `to_csv("field1,field2")` | Format as CSV rows |
| `to_jsonl` | Format as JSON Lines |

### Examples

```yaml
# Extract and deduplicate hosts from scan results
run: |
  echo "{{ steps['scan'].outputs.typed_outputs | ports | pluck('host') | unique_by('host') | sort_by('host') | to_lines }}"

# Count ports per host
run: |
  {% set counts = steps['scan'].outputs.typed_outputs | ports | count_by('host') %}
  {% for host, n in counts.items() %}
  echo "{{ host }}: {{ n }} ports"
  {% endfor %}

# Filter and format as CSV
run: |
  echo "{{ steps['scan'].outputs.typed_outputs | ports | where('state', 'open') | to_csv('host,port,service') }}"
```

---

## OFX Template Functions

Beyond standard Jinja2, OFX provides built-in functions accessible in any template expression. See the full list at [Built-in Variables & Functions](../context-variables-functions.md).

**Commonly used:**

| Function | Description |
|----------|-------------|
| `sudo("cmd")` | Wrap command with sudo (skipped if already root) |
| `uv_install("pkg")` | Install a Python package with uv |
| `go_install("pkg@ver")` | Install a Go binary |
| `file_read("path")` | Read file contents |
| `file_write("content", "path")` | Write content to file |
| `b64encode("text")` | Base64 encode |
| `random_string(16)` | Generate random string |
| `local_ip()` | Get local IP address |
| `export_typed_outputs(path, items)` | Export typed outputs to project directories |

---

## See Also
- [Template Examples](examples.md)
- [Built-in Variables & Functions](../context-variables-functions.md)
- [Templates Overview](../templates.md)
