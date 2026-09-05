# Utility Workflows

Target parsing, IOC extraction, and results export for reporting.

## Workflows

### parse-targets
Normalize IPs, CIDRs, domains, and URLs from input sources into clean target lists.
```bash
ofx flow run utility/parse-targets --input target=mixed_targets.txt
```

### extract-iocs
Extract IPs, domains, URLs, hashes, and email addresses from scan results.
```bash
ofx flow run utility/extract-iocs --input target=scan_results/
```

### export-results
Convert scan findings to JSON, CSV, or Markdown reports.
```bash
ofx flow run utility/export-results --input target=scan_results/ --input format=markdown
```

### classify-target
Detect whether targets are domains, subdomains, CIDR ranges, IPs, or URLs and split them into typed lists for downstream workflows.
```bash
ofx flow run utility/classify-target --input target=example.com
ofx flow run utility/classify-target --input target=mixed.txt
```
