import asyncio
import logging
from pathlib import Path

from ofx.commands.flow.visualize import VisualizeHandler

from ofx.commands.flow.run import FlowRunHandler
from ofx.commands.flow.tools import ToolsInstallHandler
from ofx.commands.flow.validate import ValidateHandler
from ofx.utils.args import parse_key_value_pairs

# Setup simple logging
logging.basicConfig(level=logging.INFO)


async def test_refactor():
    print("--- Starting Manual Verification ---")

    # 1. Create dummy workflow
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
        # 2. Test Utils
        print("\n--- Testing ofx.utils.args ---")
        inputs = ["key=value", "json={'a':1}"]
        parsed = parse_key_value_pairs(inputs)
        print(f"Parsed inputs: {parsed}")
        assert parsed["key"] == "value"
        assert parsed["json"] == {"a": 1}
        print("Args parsing passed.")

        # 3. Test Validate
        print("\n--- Testing ValidateHandler ---")
        ValidateHandler().run("test_flow")
        print("Validation passed.")

        # 4. Test Tools
        print("\n--- Testing ToolsInstallHandler ---")
        # We mock the installer run to avoid actual installation attempts,
        # but we want to see if it finds the tools.
        handler = ToolsInstallHandler(workflow_name="test_flow")
        # The run method is async and calls installer.run().
        # We can just check `_collect_tools_from_workflows` if we want to be unit-test style,
        # but calling run() verifies the whole chain up to execution.
        # It's fine if it tries to install curl (it will fail or skip if system check fails, but logic holds).
        # Actually, let's just inspect what it finds to be safe.
        tools = handler._collect_tools_from_workflows([Path("test_flow.yml")])
        print(f"Found tools: {tools}")
        assert "curl" in tools
        print("Tools collection passed.")

        # 5. Test Visualize
        print("\n--- Testing VisualizeHandler ---")
        # Output to console
        VisualizeHandler(workflow_name="test_flow").run()
        print("Visualization passed.")

        # 6. Test FlowRunHandler initialization
        print("\n--- Testing FlowRunHandler Init ---")
        handler = FlowRunHandler("test_flow", input=["foo=bar"])
        # handler._process_inputs() is called inside run(), let's peek?
        # No, _process_inputs was removed/inlined. It's inside run().
        # We can't easily run() without side effects.
        # But we verified parse_key_value_pairs above.
        print("FlowRunHandler initialized.")

    finally:
        # Cleanup
        if Path("test_flow.yml").exists():
            Path("test_flow.yml").unlink()
            print("\nCleaned up test_flow.yml")


if __name__ == "__main__":
    asyncio.run(test_refactor())
