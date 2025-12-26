"""Result exporters for workflow execution results.

Provides multiple export formats for analysis and reporting:
- JSON: Machine-readable structured data
- CSV: Tabular data for spreadsheets
- HTML: Human-readable reports
- Markdown: Documentation-friendly format
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from jinja2 import Template


class ResultExporter:
    """Base class for result exporters."""
    
    def __init__(self, results: Dict[str, Any]):
        self.results = results
        self.timestamp = datetime.now()
    
    def export(self, output_path: Path) -> None:
        """Export results to specified path."""
        raise NotImplementedError


class JSONExporter(ResultExporter):
    """Export results as JSON."""
    
    def export(self, output_path: Path, indent: int = 2) -> None:
        """Export results to JSON file."""
        output_path = Path(output_path).with_suffix('.json')
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=indent, default=str)


class CSVExporter(ResultExporter):
    """Export results as CSV (flattened structure)."""
    
    def export(self, output_path: Path) -> None:
        """Export results to CSV file."""
        output_path = Path(output_path).with_suffix('.csv')
        
        # Flatten nested structure for CSV
        rows = self._flatten_results(self.results)
        
        if not rows:
            return
        
        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    
    def _flatten_results(self, data: Dict, prefix: str = '') -> List[Dict]:
        """Flatten nested dictionary structure."""
        rows = []
        
        def flatten(d: Any, parent_key: str = ''):
            if isinstance(d, dict):
                for k, v in d.items():
                    new_key = f"{parent_key}.{k}" if parent_key else k
                    if isinstance(v, (dict, list)):
                        flatten(v, new_key)
                    else:
                        row[new_key] = v
            elif isinstance(d, list):
                for i, item in enumerate(d):
                    flatten(item, f"{parent_key}[{i}]")
        
        row = {}
        flatten(data)
        if row:
            rows.append(row)
        
        return rows


class HTMLExporter(ResultExporter):
    """Export results as HTML report."""
    
    HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>OFX Workflow Report - {{ workflow_name }}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .header h1 { margin: 0 0 10px 0; }
        .header p { margin: 5px 0; opacity: 0.9; }
        .section {
            background: white;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .section h2 {
            margin-top: 0;
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        .job {
            border-left: 4px solid #667eea;
            padding-left: 15px;
            margin-bottom: 20px;
        }
        .step {
            background: #f9f9f9;
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .success { border-left-color: #10b981; }
        .failed { border-left-color: #ef4444; }
        .status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .status.completed { background: #d1fae5; color: #065f46; }
        .status.failed { background: #fee2e2; color: #991b1b; }
        .status.running { background: #dbeafe; color: #1e40af; }
        pre {
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }
        .metadata {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }
        .metadata-item {
            background: #f9fafb;
            padding: 10px;
            border-radius: 5px;
        }
        .metadata-item label {
            font-size: 12px;
            color: #6b7280;
            text-transform: uppercase;
            font-weight: 600;
        }
        .metadata-item value {
            display: block;
            margin-top: 5px;
            font-size: 14px;
            color: #111827;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 {{ workflow_name }}</h1>
        <p>Status: <span class="status {{ status|lower }}">{{ status }}</span></p>
        <p>Executed: {{ timestamp }}</p>
        <p>Run ID: <code>{{ run_id }}</code></p>
    </div>

    {% if jobs %}
    <div class="section">
        <h2>📋 Jobs & Steps</h2>
        {% for job_id, job in jobs.items() %}
        <div class="job {{ job.status|lower }}">
            <h3>{{ job.name or job_id }}</h3>
            <p>Status: <span class="status {{ job.status|lower }}">{{ job.status }}</span></p>
            
            {% if job.steps %}
            <div class="steps">
                {% for step_id, step in job.steps.items() %}
                <div class="step">
                    <strong>{{ step.name }}</strong>
                    <span class="status {{ step.status|lower }}">{{ step.status }}</span>
                    
                    {% if step.outputs %}
                    <details>
                        <summary>Outputs</summary>
                        <pre>{{ step.outputs|tojson(indent=2) }}</pre>
                    </details>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endif %}

    {% if outputs %}
    <div class="section">
        <h2>📤 Outputs</h2>
        <pre>{{ outputs|tojson(indent=2) }}</pre>
    </div>
    {% endif %}

    {% if metadata %}
    <div class="section">
        <h2>ℹ️ Metadata</h2>
        <div class="metadata">
            {% for key, value in metadata.items() %}
            <div class="metadata-item">
                <label>{{ key }}</label>
                <value>{{ value }}</value>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <div class="section" style="text-align: center; color: #9ca3af; font-size: 12px;">
        Generated by OFX - Offensive Flow Executor
    </div>
</body>
</html>
    """
    
    def export(self, output_path: Path) -> None:
        """Export results to HTML file."""
        output_path = Path(output_path).with_suffix('.html')
        
        template = Template(self.HTML_TEMPLATE)
        html = template.render(
            workflow_name=self.results.get('name', 'Workflow'),
            status=self.results.get('status', 'unknown'),
            timestamp=self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            run_id=self.results.get('run_id', 'N/A'),
            jobs=self.results.get('outputs', {}).get('jobs', {}),
            outputs=self.results.get('outputs', {}),
            metadata=self.results.get('metadata', {}),
        )
        
        with open(output_path, 'w') as f:
            f.write(html)


class MarkdownExporter(ResultExporter):
    """Export results as Markdown."""
    
    def export(self, output_path: Path) -> None:
        """Export results to Markdown file."""
        output_path = Path(output_path).with_suffix('.md')
        
        md_lines = [
            f"# Workflow Report: {self.results.get('name', 'Workflow')}",
            "",
            f"**Status:** {self.results.get('status', 'unknown')}",
            f"**Executed:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Run ID:** `{self.results.get('run_id', 'N/A')}`",
            "",
        ]
        
        # Add jobs section
        jobs = self.results.get('outputs', {}).get('jobs', {})
        if jobs:
            md_lines.extend(["## Jobs", ""])
            for job_id, job in jobs.items():
                md_lines.append(f"### {job.get('name', job_id)}")
                md_lines.append(f"**Status:** {job.get('status', 'unknown')}")
                md_lines.append("")
                
                steps = job.get('steps', {})
                if steps:
                    md_lines.append("#### Steps")
                    md_lines.append("")
                    for step_id, step in steps.items():
                        md_lines.append(f"- **{step.get('name', step_id)}**: {step.get('status', 'unknown')}")
                    md_lines.append("")
        
        # Add outputs section
        outputs = self.results.get('outputs', {})
        if outputs:
            md_lines.extend(["## Outputs", "", "```json"])
            md_lines.append(json.dumps(outputs, indent=2, default=str))
            md_lines.extend(["```", ""])
        
        with open(output_path, 'w') as f:
            f.write('\n'.join(md_lines))


def export_results(
    results: Dict[str, Any],
    output_path: Path,
    formats: List[str] = None
) -> List[Path]:
    """Export results in multiple formats.
    
    Args:
        results: Workflow execution results
        output_path: Base path for output files (without extension)
        formats: List of formats to export ('json', 'csv', 'html', 'markdown')
                If None, exports all formats
    
    Returns:
        List of generated file paths
    """
    if formats is None:
        formats = ['json', 'html', 'markdown']
    
    exporters = {
        'json': JSONExporter,
        'csv': CSVExporter,
        'html': HTMLExporter,
        'markdown': MarkdownExporter,
        'md': MarkdownExporter,
    }
    
    exported_files = []
    
    for fmt in formats:
        fmt = fmt.lower()
        if fmt in exporters:
            exporter = exporters[fmt](results)
            exporter.export(output_path)
            exported_files.append(
                Path(output_path).with_suffix(f'.{fmt if fmt != "markdown" else "md"}')
            )
    
    return exported_files


__all__ = [
    'ResultExporter',
    'JSONExporter',
    'CSVExporter',
    'HTMLExporter',
    'MarkdownExporter',
    'export_results',
]
