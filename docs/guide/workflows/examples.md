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
```yaml
name: Scan with Outputs
jobs:
  scan:
    name: Port Scan
    steps:
      - name: Scan target
        run: nmap {{ inputs.target }}
        outputs:
          open_ports: "{{ step.stdout_lines }}"
  report:
    name: Generate Report
    needs: scan
    steps:
      - name: Display results
        run: echo "Ports: {{ jobs.scan.outputs.open_ports }}"
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

## Example 6: Interactive Debugging
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

## Example 7: Comprehensive Web Reconnaissance
This example demonstrates a multi-job workflow that takes a domain, finds subdomains, checks for open web ports, and generates a report.

```yaml
name: Comprehensive Web Recon
inputs:
  domain:
    description: The target domain to scan.
    required: true
secrets:
  FOFA_USER:
    required: false
  FOFA_TOKEN:
    required: false

jobs:
  discover-subdomains:
    name: Discover Subdomains
    steps:
      - name: Search with Fofa
        script: |
          from ofx.api.search import Fofa
          fofa = Fofa(user="${{ secrets.FOFA_USER }}", token="${{ secrets.FOFA_TOKEN }}")
          results = fofa.search(f'domain="{{ inputs.domain }}"')
          # Extract host from results
          hosts = [res.split('//')[1].split(':')[0] for res in results]
          print('\n'.join(hosts))
        outputs:
          subdomains: "{{ step.stdout_lines }}"

  check-web-ports:
    name: Check for Open Web Ports
    needs: discover-subdomains
    steps:
      - name: Check ports 80 and 443
        script: |
          from ofx.api.exploit import check_port
          
          open_hosts = []
          subdomains = {{ jobs.discover-subdomains.outputs.subdomains }}
          for host in subdomains:
              if check_port(host, 80):
                  open_hosts.append(f"http://{host}")
              if check_port(host, 443):
                  open_hosts.append(f"https://{host}")
          
          print('\n'.join(open_hosts))
        outputs:
          live_hosts: "{{ step.stdout_lines }}"

  generate-report:
    name: Generate Report
    needs: check-web-ports
    steps:
      - name: Fetch titles and generate report
        script: |
          from ofx.api.http import fetch
          from ofx.api.file import write_file
          import re

          live_hosts = {{ jobs.check-web-ports.outputs.live_hosts }}
          report = "# Web Reconnaissance Report\n\n"
          report += f"## Target: {{ inputs.domain }}\n\n"
          
          for host in live_hosts:
              try:
                  content = fetch(host, timeout=5)
                  title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
                  title = title_match.group(1).strip() if title_match else "No Title Found"
                  report += f"- **{host}**: {title}\n"
              except Exception as e:
                  report += f"- **{host}**: Failed to fetch ({e})\n"
          
          write_file(report, "${{ ctx.output_path }}/recon_report.md")
          print(f"Report saved to ${{ ctx.output_path }}/recon_report.md")

```

---

## See Also
- [Workflow Stages](stages.md)
- [Dependencies](dependencies.md)
