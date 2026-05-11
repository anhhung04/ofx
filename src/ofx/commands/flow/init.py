"""Workflow initialization handler."""

import json
import logging
from pathlib import Path

import typer

from ofx.commands.ui_helpers import print_success, print_warning
from ofx.settings import BASE_DATA_DIR, ensure_dir, settings

logger = logging.getLogger(settings.app_branding)

WORKFLOW_TEMPLATE = """\
# yaml-language-server: $schema={schema_path}
name: {name}
description: Describe what this workflow does
tags:
  - example

dispatch:
  inputs:
    target:
      required: true
      type: string
      description: Primary target
      alias: t

jobs:
  scan:
    name: Scan Target
    steps:
      - name: port_scan
        run: |
            echo "Scanning {{{{ inputs.target }}}}..."
            echo "result=success" >> "$OFX_OUTPUTS"

      # Uncomment to use a task wrapper:
      # - name: nmap_scan
      #   task: nmap
      #   with:
      #     target: '{{{{ inputs.target }}}}'

      # Uncomment for declarative data transformation:
      # - name: filter_results
      #   pipe:
      #     input: '{{{{ steps["nmap_scan"].outputs.typed_outputs }}}}'
      #     filter: "port > 1024"
      #     sort: port
      #     format: csv
      #     field: host,port

      # Uncomment for inline Python:
      # - name: process
      #   script: |
      #       data = {{"target": "{{{{ inputs.target }}}}"}}
      #       add_outputs(processed=True, data=data)

  # Uncomment for a dependent job:
  # report:
  #   name: Generate Report
  #   needs: [scan]
  #   steps:
  #     - run: echo "Scan result: {{{{ jobs.scan.outputs.result }}}}"

"""


class FlowInitHandler:
    """Creates a new workflow file pre-configured for YAML language server."""

    def run(self, workflow_name: str, output: str, force: bool) -> None:
        schema_path = self._ensure_schema()
        output_path = self._resolve_output(workflow_name, output)

        if output_path.exists() and not force:
            print_warning(
                "File Exists",
                f"Workflow file already exists: {output_path}",
                "Use --force to overwrite.",
            )
            raise typer.Exit(1)

        content = WORKFLOW_TEMPLATE.format(name=workflow_name, schema_path=schema_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)

        print_success(
            "Workflow Created",
            f"Workflow [cyan]{workflow_name}[/cyan] initialized.",
            {
                "File": str(output_path),
                "Schema": str(schema_path),
            },
        )

    def _ensure_schema(self) -> Path:
        """Export the workflow JSON schema to ~/.ofx/ and return its path."""
        from ofx.models.workflow import Workflow

        schema_dir = ensure_dir(BASE_DATA_DIR)
        schema_path = schema_dir / "workflow_schema.json"
        schema = Workflow.model_json_schema()
        schema_path.write_text(json.dumps(schema, indent=2))
        logger.debug(f"Workflow schema written to {schema_path}")
        return schema_path

    def _resolve_output(self, workflow_name: str, output: str) -> Path:
        """Derive the output file path from the name and optional override."""
        if output:
            p = Path(output)
            # If output is an existing directory, place the file inside it
            if p.is_dir():
                return p / f"{workflow_name}.yml"
            return p
        return Path.cwd() / f"{workflow_name}.yml"
