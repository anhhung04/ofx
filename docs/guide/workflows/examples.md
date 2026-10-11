# Workflow Examples

This page provides practical OFX workflow examples for common red teaming, automation, and DevSecOps scenarios.

---

## Example 1: Simple Reconnaissance
```yaml
name: Web Recon
jobs:
  scan:
    name: Scan Target
    steps:
      - name: Run nmap scan
        module: shell
        with:
          cmd: nmap {{ inputs.target }}
```

---

## Example 2: Multi-Stage Exploitation
```yaml
name: Exploit Chain
jobs:
  recon:
    name: Reconnaissance
    steps:
      - name: Scan target
        module: shell
        with:
          cmd: nmap {{ inputs.target }}
  exploit:
    name: Exploitation
    needs: recon
    steps:
      - name: Run exploit
        module: shell
        with:
          cmd: python exploit.py --target {{ inputs.target }}
  loot:
    name: Data Collection
    needs: exploit
    steps:
      - name: Collect loot
        module: shell
        with:
          cmd: ./loot.sh
```

---

## Example 3: Parallel Jobs
```yaml
name: Parallel Scans
jobs:
  scan1:
    name: Scan Host 1
    steps:
      - name: Scan 10.0.0.1
        module: shell
        with:
          cmd: nmap 10.0.0.1
  scan2:
    name: Scan Host 2
    steps:
      - name: Scan 10.0.0.2
        module: shell
        with:
          cmd: nmap 10.0.0.2
```

---

## Example 4: Using Outputs

Use OFX_OUTPUTS to pass data between jobs:

```yaml
name: Scan with Outputs
jobs:
  scan:
    name: Port Scan
    outputs:
      open_ports: "{{ steps.0.outputs.open_ports }}"
    steps:
      - name: Scan and capture ports
        module: shell
        with:
          cmd: |
            # Run scan and extract open ports
            nmap {{ inputs.target }} | grep "^[0-9]" | cut -d'/' -f1 > ports.txt
            # Save to outputs
            echo "open_ports=$(cat ports.txt | tr '\n' ',')" >> $OFX_OUTPUTS

  report:
    name: Generate Report
    needs: [scan]
    steps:
      - name: Display results
        module: shell
        with:
          cmd: 'echo "Open ports: {{ jobs.scan.outputs.open_ports }}"'
```

---

## Example 5: With Secrets
```yaml
name: API Request
jobs:
  api:
    name: Call API
    steps:
      - name: Make authenticated request
        module: shell
        with:
          cmd: 'curl -H "Authorization: Bearer {{ secrets.API_KEY }}" https://api.example.com'
```

---

## Example 6: Inter-Job Communication with Channels
```yaml
name: Channel Communication
jobs:
  producer:
    name: Data Producer
    steps:
      - name: Generate and publish data
        module: python
        with:
          script: |
            import time
            results = []
            for i in range(3):
                results.append(f"result_{i}")
                publish('progress', {'count': i+1, 'results': results})
                time.sleep(1)
            publish('final', {'status': 'complete', 'data': results})

  consumer:
    name: Data Consumer  
    needs: producer
    steps:
      - name: Wait for completion
        module: python
        with:
          script: |
            # Wait for final results
            final_data = wait_for('final', lambda d: d.get('status') == 'complete')
            print(f"Final results: {final_data['data']}")

      - name: Monitor progress
        module: python
        with:
          script: |
            # Subscribe to progress updates
            gen = subscribe('progress')
            for update in gen:
                print(f"Progress: {update['count']}/3 - {update['results']}")
                if update['count'] >= 3:
                    break
```

Channels enable asynchronous communication between jobs, allowing producers to send updates that consumers can react to in real-time.

---

## Example 7: Interactive Debugging
```yaml
name: Debug Session
jobs:
  debug:
    name: Interactive Debug
    steps:
      - name: Launch bash shell
        module: shell
        with:
          cmd: bash
        interactive: true
        timeout: 10
```

---

## Example 8: Reusable Workflow from GitHub

This example calls a reusable workflow hosted in a GitHub repo. OFX will clone the repo and load its main workflow file.

```yaml
name: Repo Reuse Example

jobs:
  run-recon:
    steps:
      - name: Run recon workflow
        uses: https://github.com/user/recon-workflows
```

---

## Example 9: Comprehensive Web Reconnaissance

This example demonstrates a multi-job workflow that takes a domain, finds subdomains, checks for open web ports, and generates a report.

```yaml
name: Comprehensive Web Recon

dispatch:
  inputs:
    domain:
      description: The target domain to scan
      required: true

call:
  secrets:
    FOFA_USER:
      required: false
    FOFA_TOKEN:
      required: false

jobs:
  discover_subdomains:
    name: Discover Subdomains
    outputs:
      subdomains: "{{ steps.0.outputs.subdomains }}"
    steps:
      - name: Search with FOFA
        module: python
        with:
          script: |
            from ofx.api.search import FofaClient
            import os

            fofa = FofaClient(
                user=os.getenv('FOFA_USER', '{{ secrets.FOFA_USER }}'),
                token=os.getenv('FOFA_TOKEN', '{{ secrets.FOFA_TOKEN }}')
            )
            results = fofa.search(f'domain="{{ inputs.domain }}"')

            # Extract hosts from results
            hosts = [res.split('//')[1].split(':')[0] for res in results]

            # Save to outputs
            with open(os.getenv('OFX_OUTPUTS'), 'a') as f:
                f.write(f"subdomains={','.join(hosts)}\n")
  check_web_ports:
    name: Check for Open Web Ports
    needs: [discover_subdomains]
    outputs:
      live_hosts: "{{ steps.0.outputs.live_hosts }}"
    steps:
      - name: Check ports 80 and 443
        module: python
        with:
          script: |
            from ofx.api.exploitation.exploit.utils import check_port
            import os

            subdomains = "{{ jobs.discover_subdomains.outputs.subdomains }}".split(',')
            open_hosts = []

            for host in subdomains:
                if host:
                    if check_port(host, 80):
                        open_hosts.append(f"http://{host}")
                    if check_port(host, 443):
                        open_hosts.append(f"https://{host}")

            # Save to outputs
            with open(os.getenv('OFX_OUTPUTS'), 'a') as f:
                f.write(f"live_hosts={','.join(open_hosts)}\n")
  generate_report:
    name: Generate Report
    needs: [check_web_ports]
    steps:
      - name: Fetch titles and generate report
        module: python
        with:
          script: |
            from ofx.api.http import fetch
            from ofx.api.file import write_file
            import re

            live_hosts = "{{ jobs.check_web_ports.outputs.live_hosts }}".split(',')
            report = "# Web Reconnaissance Report\n\n"
            report += f"## Target: {{ inputs.domain }}\n\n"

            for host in live_hosts:
                if host:
                    try:
                        content = fetch(host, timeout=5)
                        title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
                        title = title_match.group(1).strip() if title_match else "No Title Found"
                        report += f"- **{host}**: {title}\n"
                    except Exception as e:
                        report += f"- **{host}**: Failed to fetch ({str(e)})\n"

            output_file = "{{ ctx.output_path }}/recon_report.md"
            write_file(report, output_file)
            print(f"Report saved to {output_file}")
```

---

## Example 10: Module-Based Recon Pipeline

Use user-defined modules for structured output parsing and data chaining between tools:

```yaml
name: Recon Pipeline

dispatch:
  inputs:
    target:
      required: true
      description: Target domain or IP

jobs:
  discover:
    steps:
      - module: modules/subfinder_enum.py
        name: find-subs
        with:
          target: "{{ inputs.target }}"

      - module: modules/http_probe.py
        name: probe-http
        with:
          target: "{{ inputs.target }}"

      - module: shell
        with:
          cmd: |
            echo "=== Discovery Results ==="
            echo "Subdomains: {{ subdomains(steps['find-subs'].outputs.typed_outputs) | length }}"
            echo "Live URLs: {{ urls(steps['probe-http'].outputs.typed_outputs) | length }}"

  vuln-scan:
    needs: [discover]
    steps:
      - module: modules/nuclei_scan.py
        name: scan-vulns
        with:
          target: "{{ inputs.target }}"
          severity: "critical,high,medium"

      - module: shell
        with:
          cmd: |
            echo "Vulnerabilities: {{ vulns(steps['scan-vulns'].outputs.typed_outputs) | length }}"
```

The modules (`modules/subfinder_enum.py`, `modules/http_probe.py`, `modules/nuclei_scan.py`) are user-defined modules that run the tool and emit `typed_outputs` via `ctx.add_outputs()` — see [Modules](../jobs-steps/steps.md#modules) for the module contract.

---

## Example 11: Matrix Strategy — Multi-Target Scanning

Scan multiple targets in parallel using matrix expansion:

```yaml
name: Multi-Target Scan

dispatch:
  inputs:
    targets:
      required: true
      description: Comma-separated target list

jobs:
  scan:
    strategy:
      matrix:
        target: ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
      max_parallel: 2
      fail_fast: false
    steps:
      - module: modules/port_scan.py
        name: port-scan
        with:
          target: "{{ matrix.target }}"
          ports: "1-1000"

      - module: shell
        with:
          cmd: echo "Scanned {{ matrix.target }} — {{ ports(steps['port-scan'].outputs.typed_outputs) | length }} open ports"
```

---

## Example 12: Cloud Job

Run a scan on a remote VPS provisioned automatically:

```yaml
name: Cloud Scan

jobs:
  remote-scan:
    cloud: do-nyc
    steps:
      - module: shell
        with:
          cmd: nmap -p 1-65535 -T4 10.0.0.0/24

  analyze:
    needs: [remote-scan]
    steps:
      - module: shell
        with:
          cmd: echo "Analysis complete"
```

The `cloud` field references a profile from `~/.ofx/cloud.yml`. OFX provisions the VPS, runs the steps remotely, and destroys it on completion.

---

## Example 13: Credential Discovery with Auto-Storage

Combine brute-force modules with automatic credential storage:

```yaml
name: Credential Discovery

defaults:
  store-creds: true

jobs:
  brute:
    steps:
      - module: modules/ssh_brute.py
        name: ssh-brute
        with:
          target: "{{ inputs.target }}"

      - module: modules/kerberos_enum.py
        name: kerberos-enum
        store-creds: false          # Override — don't store these
        with:
          target: "{{ inputs.dc }}"
```

When `store-creds` is enabled, `user_account` typed outputs from modules are automatically saved to the credential store.

---

## See Also
- [Workflow Stages](stages.md)
- [Dependencies](dependencies.md)
- 
- [Matrix Strategy](../jobs-steps/matrix-strategy.md)
- [Cloud Runners](../cloud-runners.md)
