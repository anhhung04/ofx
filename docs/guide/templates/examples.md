# Template Examples

Practical examples of Jinja2 templates in OFX workflows.

---

## Basic Variable Substitution

```yaml
module: shell
with:
  cmd: echo "Target is {{ inputs.target }}"
```

---

## Dynamic File Paths

```yaml
steps:
  - name: Save scan results
    module: shell
    with:
      cmd: |
        nmap {{ inputs.target }} -oX {{ ctx.output_path }}/scan_{{ ctx.run_id }}.xml
        echo "Saved to {{ ctx.output_path }}"
```

---

## Using Step Outputs

```yaml
steps:
  - name: find-target
    module: shell
    with:
      cmd: |
        target=$(dig +short {{ inputs.domain }} | head -1)
        echo "target_ip=$target" >> $OFX_OUTPUTS

  - name: scan-target
    module: shell
    with:
      cmd: nmap -sV {{ steps['find-target'].outputs.target_ip }}
```

---

## Typed Output Chaining

Chain module outputs between steps using helper functions. User-defined modules (see [Modules](../jobs-steps/steps.md#modules)) can run a tool and emit `typed_outputs` via `ctx.add_outputs()`:

```yaml
steps:
  - module: modules/port_scan.py
    name: port-scan
    with:
      target: "{{ inputs.target }}"
      ports: "1-10000"

  - module: modules/http_probe.py
    name: http-probe
    with:
      target: "{{ inputs.target }}"
      ports: "{{ ports(steps['port-scan'].outputs.typed_outputs) | map(attribute='port') | join(',') }}"

  - module: shell
    with:
      cmd: |
        echo "=== Results ==="
        echo "Open ports: {{ ports(steps['port-scan'].outputs.typed_outputs) | map(attribute='host_port') | join(', ') }}"
        echo "Live URLs: {{ urls(steps['http-probe'].outputs.typed_outputs) | map(attribute='url') | join(', ') }}"
```

---

## Conditional Scan Mode

```yaml
steps:
  - name: scan
    module: shell
    with:
      cmd: |
        {% if inputs.mode == "stealth" %}
        nmap -sS -T2 -Pn {{ inputs.target }}
        {% elif inputs.mode == "aggressive" %}
        nmap -A -T4 {{ inputs.target }}
        {% else %}
        nmap -sV {{ inputs.target }}
        {% endif %}
```

---

## Platform-Aware Commands

```yaml
steps:
  - name: install-tool
    module: shell
    with:
      cmd: |
        {% if is_windows %}
        choco install nmap
        {% else %}
        {{ sudo("apt-get install -y nmap") }}
        {% endif %}
```

---

## Looping Over Discovered Hosts

```yaml
steps:
  - name: scan-all
    module: shell
    with:
      cmd: |
        {% for host in jobs.discover.outputs.hosts.split(",") %}
        echo "--- Scanning {{ host }} ({{ loop.index }}/{{ loop.length }}) ---"
        nmap -sV {{ host }} -oN {{ ctx.output_path }}/{{ host }}.txt
        {% endfor %}
```

---

## Dynamic Timeout from Inputs

```yaml
steps:
  - name: comprehensive-scan
    module: shell
    with:
      cmd: nmap -sV -p 1-65535 {{ inputs.target }}
    timeout: "{{ (inputs.target_count | int / 50) | int * 1 + 15 }}"
```

---

## File Operations in Templates

```yaml
steps:
  - name: prepare-targets
    module: shell
    with:
      cmd: |
        {{ file_write(inputs.targets, ctx.output_path ~ "/targets.txt") }}
        echo "Wrote {{ inputs.targets.split('\n') | length }} targets"

  - name: read-results
    module: shell
    with:
      cmd: |
        {% set content = file_read(ctx.output_path ~ "/scan.txt") %}
        echo "Results: {{ content | length }} bytes"
```

---

## Encoding and Hashing

```yaml
steps:
  - name: prepare-payload
    module: shell
    with:
      cmd: |
        echo "Base64: {{ b64encode(inputs.payload) }}"
        echo "URL-encoded: {{ url_encode(inputs.target) }}"
        echo "SHA256: {{ sha256(inputs.target) }}"
```

---

## Random Values for Evasion

```yaml
steps:
  - name: setup-listener
    module: shell
    with:
      cmd: |
        PORT={{ random_port() }}
        TOKEN={{ random_string(32) }}
        echo "Listener on $PORT with token $TOKEN"
```

---

## Matrix Values in Templates

```yaml
jobs:
  scan:
    strategy:
      matrix:
        target: ["10.0.0.1", "10.0.0.2"]
        port: [80, 443]
    steps:
      - name: "scan-{{ matrix.target }}-{{ matrix.port }}"
        module: shell
        with:
          cmd: nmap -p {{ matrix.port }} {{ matrix.target }} -oN {{ ctx.output_path }}/{{ matrix.target }}_{{ matrix.port }}.txt
```

---

## Filtering Vulnerabilities by Severity

```yaml
steps:
  - module: modules/nuclei_scan.py
    name: vuln-scan
    with:
      target: "{{ inputs.target }}"

  - name: report
    module: shell
    with:
      cmd: |
        {% set all_vulns = vulns(steps['vuln-scan'].outputs.typed_outputs) %}
        {% set critical = all_vulns | selectattr('severity', 'eq', 'critical') | list %}
        {% set high = all_vulns | selectattr('severity', 'eq', 'high') | list %}
        echo "=== Vulnerability Summary ==="
        echo "Critical: {{ critical | length }}"
        echo "High: {{ high | length }}"
        echo "Total: {{ all_vulns | length }}"
```

---

## See Also
- [Jinja Template Reference](jinja.md)
- [Built-in Variables & Functions](../context-variables-functions.md)
- 
