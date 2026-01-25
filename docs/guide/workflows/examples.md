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
        run: nmap ${{ inputs.target }}
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
        run: nmap ${{ inputs.target }}
  exploit:
    name: Exploitation
    needs: recon
    steps:
      - name: Run exploit
        run: python exploit.py --target ${{ inputs.target }}
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
      open_ports: "${{ steps.0.outputs.open_ports }}"
    steps:
      - name: Scan and capture ports
        run: |
          # Run scan and extract open ports
          nmap ${{ inputs.target }} | grep "^[0-9]" | cut -d'/' -f1 > ports.txt
          # Save to outputs
          echo "open_ports=$(cat ports.txt | tr '\n' ',')" >> $OFX_OUTPUTS
  
  report:
    name: Generate Report
    needs: [scan]
    steps:
      - name: Display results
        run: echo "Open ports: ${{ jobs.scan.outputs.open_ports }}"
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
        run: curl -H "Authorization: Bearer ${{ secrets.API_KEY }}" https://api.example.com
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
    description: The target domain to scan
    required: true

secrets:
  FOFA_USER:
    required: false
  FOFA_TOKEN:
    required: false

jobs:
  discover_subdomains:
    name: Discover Subdomains
    outputs:
      subdomains: "${{ steps.0.outputs.subdomains }}"
    steps:
      - name: Search with FOFA
        run: |
          python << 'EOF'
          from ofx.api.search import Fofa
          import os
          
          fofa = Fofa(
              user=os.getenv('FOFA_USER', '${{ secrets.FOFA_USER }}'),
              token=os.getenv('FOFA_TOKEN', '${{ secrets.FOFA_TOKEN }}')
          )
          results = fofa.search(f'domain="${{ inputs.domain }}"')
          
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
      live_hosts: "${{ steps.0.outputs.live_hosts }}"
    steps:
      - name: Check ports 80 and 443
        run: |
          python << 'EOF'
          from ofx.api.exploitation.exploit.utils import check_port
          import os
          
          subdomains = "${{ jobs.discover_subdomains.outputs.subdomains }}".split(',')
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
          
          live_hosts = "${{ jobs.check_web_ports.outputs.live_hosts }}".split(',')
          report = "# Web Reconnaissance Report\n\n"
          report += f"## Target: ${{ inputs.domain }}\n\n"
          
          for host in live_hosts:
              if host:
                  try:
                      content = fetch(host, timeout=5)
                      title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
                      title = title_match.group(1).strip() if title_match else "No Title Found"
                      report += f"- **{host}**: {title}\n"
                  except Exception as e:
                      report += f"- **{host}**: Failed to fetch ({str(e)})\n"
          
          output_file = "${{ ctx.output_path }}/recon_report.md"
          write_file(report, output_file)
          print(f"Report saved to {output_file}")
          EOF
```

---

## See Also
- [Workflow Stages](stages.md)
- [Dependencies](dependencies.md)
