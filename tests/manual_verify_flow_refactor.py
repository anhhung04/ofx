import asyncio
import logging
from pathlib import Path

from ofx.commands.flow.run import FlowRunHandler
from ofx.commands.flow.tools import ToolsInstallHandler
from ofx.commands.flow.validate import ValidateHandler
from ofx.commands.flow.visualize import VisualizeHandler
from ofx.utils.args import parse_key_value_pairs

logging.basicConfig(level=logging.INFO)

async def test_refactor():
    print("--- Starting Manual Verification ---")

    flow_content = """
name: test_flow
description: A test workflow
jobs:
  job1:
    steps:
      - name: step1
        run: echo "Hello"
tools:
  curl: "sudo apt install curl"
"""
    Path("test_flow.yml").write_text(flow_content)
    print("Created test_flow.yml")

    try:
        print("\n--- Testing ofx.utils.args ---")
        inputs = ["key=value", "json={'a':1}"]
        parsed = parse_key_value_pairs(inputs)
        print(f"Parsed inputs: {parsed}")
        assert parsed["key"] == "value"
        assert parsed["json"] == {"a": 1}
        print("Args parsing passed.")

        print("\n--- Testing ValidateHandler ---")
        ValidateHandler().run("test_flow")
        print("Validation passed.")

        print("\n--- Testing ToolsInstallHandler ---")
        handler = ToolsInstallHandler(workflow_name="test_flow")
        tools = handler._collect_tools_from_workflows([Path("test_flow.yml")])
        print(f"Found tools: {tools}")
        assert "curl" in tools
        print("Tools collection passed.")

        print("\n--- Testing VisualizeHandler ---")
        VisualizeHandler(workflow_name="test_flow").run()
        print("Visualization passed.")

        print("\n--- Testing FlowRunHandler Init ---")
        handler = FlowRunHandler("test_flow", input=["foo=bar"])
        print("FlowRunHandler initialized.")

    finally:
        if Path("test_flow.yml").exists():
            Path("test_flow.yml").unlink()
            print("\nCleaned up test_flow.yml")

if __name__ == "__main__":
    asyncio.run(test_refactor())
