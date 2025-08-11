import pytest
import asyncio
import pytest_asyncio
from unittest.mock import patch, MagicMock
import logging

from ofx.commands.flow.run import FlowRunHandler


class TestFlowRunHandler:
    @pytest.fixture
    def flow_handler(self):
        return FlowRunHandler(
            workflow_name="test_workflow",
            input=["param1=value1", "param2=[1, 2, 3]", 'param3={"key": "value"}'],
            output="test_output",
        )

    def test_process_inputs(self, flow_handler):
        flow_handler._process_inputs()
        assert flow_handler.input == {
            "param1": "value1",
            "param2": [1, 2, 3],
            "param3": {"key": "value"},
        }

    def test_render_input_as_table(self, flow_handler):
        flow_handler._process_inputs()
        table = flow_handler._render_input_as_table()

        # Check that the table contains our input keys
        assert "param1" in table
        assert "param2" in table
        assert "param3" in table

        # Check that the table has a grid format (contains +---+ characters)
        assert "+-" in table
        assert "-+" in table

    @pytest.mark.asyncio
    @patch("ofx.commands.flow.run.logger")
    async def test_run_with_table_rendering(self, mock_logger, flow_handler):
        # Mock the FlowRunManager directly on the instance
        flow_handler.manager = MagicMock()
        flow_handler.manager.add = MagicMock()

        # Create a mock coroutine for wait
        async def mock_wait():
            return None

        flow_handler.manager.wait = mock_wait

        await flow_handler.run()

        # Check that the log message contains a table
        log_message = mock_logger.info.call_args[0][0]
        assert "Starting to run workflow" in log_message
        assert "+" in log_message  # Should contain table formatting characters
        assert "param1" in log_message
        assert "param2" in log_message
        assert "param3" in log_message
