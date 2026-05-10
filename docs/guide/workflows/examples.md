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
        run: nmap {{ inputs.target }}
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
        run: nmap {{ inputs.target }}
  exploit:
    name: Exploitation
    needs: recon
    steps:
      - name: Run exploit
        run: python exploit.py --target {{ inputs.target }}
  loot:
    name: Data Collection
    needs: exploit
    steps:
      - name: Collect loot
        run: ./loot.sh
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
        run: nmap 10.0.0.1
  scan2:
    name: Scan Host 2
    steps:
      - name: Scan 10.0.0.2
        run: nmap 10.0.0.2
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
        run: |
          # Run scan and extract open ports
          nmap {{ inputs.target }} | grep "^[0-9]" | cut -d'/' -f1 > ports.txt
          # Save to outputs
          echo "open_ports=$(cat ports.txt | tr '\n' ',')" >> $OFX_OUTPUTS
  
  report:
    name: Generate Report
    needs: [scan]
    steps:
      - name: Display results
        run: echo "Open ports: {{ jobs.scan.outputs.open_ports }}"
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
        run: curl -H "Authorization: Bearer {{ secrets.API_KEY }}" https://api.example.com
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
        script: |
          # Wait for final results
          final_data = wait_for('final', lambda d: d.get('status') == 'complete')
          print(f"Final results: {final_data['data']}")
          
      - name: Monitor progress
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
        run: bash
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
        run: |
          python << 'EOF'
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
          EOF

  check_web_ports:
    name: Check for Open Web Ports
    needs: [discover_subdomains]
    outputs:
      live_hosts: "{{ steps.0.outputs.live_hosts }}"
    steps:
      - name: Check ports 80 and 443
        run: |
          python << 'EOF'
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
          EOF

  generate_report:
    name: Generate Report
    needs: [check_web_ports]
    steps:
      - name: Fetch titles and generate report
        run: |
          python << 'EOF'
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
          EOF
```

---

## Example 10: Task-Based Recon Pipeline

Use task steps for structured output parsing and data chaining between tools:

```yaml
name: Task Recon Pipeline

dispatch:
  inputs:
    target:
      required: true
      description: Target domain or IP

jobs:
  discover:
    steps:
      - task: subfinder
        name: find-subs
        with:
          target: "{{ inputs.target }}"
          all: true

      - task: httpx
        name: probe-http
        with:
          target: "{{ inputs.target }}"
          tech_detect: true
          status_code: true

      - run: |
          echo "=== Discovery Results ==="
          echo "Subdomains: {{ subdomains(steps['find-subs'].outputs.typed_outputs) | length }}"
          echo "Live URLs: {{ urls(steps['probe-http'].outputs.typed_outputs) | length }}"

  vuln-scan:
    needs: [discover]
    steps:
      - task: nuclei
        name: scan-vulns
        with:
          target: "{{ inputs.target }}"
          severity: "critical,high,medium"
          tags: "cve"

      - run: |
          echo "Vulnerabilities: {{ vulns(steps['scan-vulns'].outputs.typed_outputs) | length }}"
```

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
      - task: nmap
        name: port-scan
        with:
          target: "{{ matrix.target }}"
          ports: "1-1000"
          version_detection: true

      - run: echo "Scanned {{ matrix.target }} — {{ ports(steps['port-scan'].outputs.typed_outputs) | length }} open ports"
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
      - task: nmap
        with:
          target: "10.0.0.0/24"
          ports: "1-65535"
          timing: 4

  analyze:
    needs: [remote-scan]
    steps:
      - run: echo "Analysis complete"
```

The `cloud` field references a profile from `~/.ofx/cloud.yml`. OFX provisions the VPS, runs the steps remotely, and destroys it on completion.

---

## Example 13: Credential Discovery with Auto-Storage

Combine brute-force tools with automatic credential storage:

```yaml
name: Credential Discovery

defaults:
  store-creds: true

jobs:
  brute:
    steps:
      - task: hydra
        name: ssh-brute
        with:
          target: "{{ inputs.target }}"

      - task: kerbrute
        name: kerberos-enum
        store-creds: false          # Override — don't store these
        with:
          target: "{{ inputs.dc }}"
```

When `store-creds` is enabled, `UserAccount` outputs from task steps are automatically saved to the credential store.

---

## See Also
- [Workflow Stages](stages.md)
- [Dependencies](dependencies.md)
- [Tasks](../tasks.md)
- [Matrix Strategy](../jobs-steps/matrix-strategy.md)
- [Cloud Runners](../cloud-runners.md)
