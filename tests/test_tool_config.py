import pytest
from pydantic import ValidationError
from ofx.models.workflow import Workflow, ToolConfig


def test_tool_config_with_install_only():
    """Test ToolConfig with only install command."""
    config = ToolConfig(install="apt-get install tool")
    assert config.install == "apt-get install tool"
    assert config.check is None
    assert config.install_dir is None
    assert config.post_install is None


def test_tool_config_full():
    """Test ToolConfig with all fields."""
    config = ToolConfig(
        install="mkdir -p $INSTALL_DIR && cp tool $INSTALL_DIR",
        check="ls /custom/path/tool",
        install_dir="/custom/path",
        post_install="echo 'Setup complete'",
    )
    assert config.install == "mkdir -p $INSTALL_DIR && cp tool $INSTALL_DIR"
    assert config.check == "ls /custom/path/tool"
    assert config.install_dir == "/custom/path"
    assert config.post_install == "echo 'Setup complete'"


def test_tool_config_missing_install():
    """Test that ToolConfig requires install command."""
    with pytest.raises(ValidationError):
        ToolConfig(check="which tool")


def test_workflow_tools_string_format():
    """Test workflow with simple string tool format."""
    workflow_dict = {
        "name": "Test Workflow",
        "tools": {"jq": "apt-get install -y jq", "curl": "apt-get install -y curl"},
        "jobs": {
            "test": {
                "name": "Test Job",
                "steps": [{"name": "Test Step", "run": "echo test"}],
            }
        },
    }
    workflow = Workflow(**workflow_dict)
    assert workflow.tools is not None
    assert "jq" in workflow.tools
    assert "curl" in workflow.tools

    # Check that strings were normalized to ToolConfig
    jq_tool = workflow.tools["jq"]
    assert isinstance(jq_tool, (dict, ToolConfig))


def test_workflow_tools_dict_format():
    """Test workflow with dictionary tool format."""
    workflow_dict = {
        "name": "Test Workflow",
        "tools": {
            "custom_tool": {
                "install": "mkdir -p $INSTALL_DIR && echo 'installed' > $INSTALL_DIR/tool",
                "check": "ls /tmp/tools/tool",
                "install_dir": "/tmp/tools",
                "post_install": "chmod +x /tmp/tools/tool",
            }
        },
        "jobs": {
            "test": {
                "name": "Test Job",
                "steps": [{"name": "Test Step", "run": "echo test"}],
            }
        },
    }
    workflow = Workflow(**workflow_dict)
    assert workflow.tools is not None
    assert "custom_tool" in workflow.tools

    tool = workflow.tools["custom_tool"]
    if isinstance(tool, dict):
        assert (
            tool["install"]
            == "mkdir -p $INSTALL_DIR && echo 'installed' > $INSTALL_DIR/tool"
        )
        assert tool["check"] == "ls /tmp/tools/tool"
        assert tool["install_dir"] == "/tmp/tools"
        assert tool["post_install"] == "chmod +x /tmp/tools/tool"


def test_workflow_tools_mixed_format():
    """Test workflow with mixed string and dict tool formats."""
    workflow_dict = {
        "name": "Test Workflow",
        "tools": {
            "jq": "apt-get install -y jq",
            "custom_tool": {
                "install": "mkdir -p /tmp/custom",
                "install_dir": "/tmp/custom",
            },
        },
        "jobs": {
            "test": {
                "name": "Test Job",
                "steps": [{"name": "Test Step", "run": "echo test"}],
            }
        },
    }
    workflow = Workflow(**workflow_dict)
    assert workflow.tools is not None
    assert "jq" in workflow.tools
    assert "custom_tool" in workflow.tools


def test_workflow_tools_invalid_format():
    """Test that workflow rejects invalid tool format."""
    workflow_dict = {
        "name": "Test Workflow",
        "tools": {"invalid_tool": 123},  # Invalid: should be string or dict
        "jobs": {
            "test": {
                "name": "Test Job",
                "steps": [{"name": "Test Step", "run": "echo test"}],
            }
        },
    }
    with pytest.raises(ValidationError):
        Workflow(**workflow_dict)


def test_workflow_tools_missing_install_key():
    """Test that workflow rejects dict without install key."""
    workflow_dict = {
        "name": "Test Workflow",
        "tools": {
            "bad_tool": {
                "check": "which tool",
                "install_dir": "/tmp",
                # Missing required 'install' key
            }
        },
        "jobs": {
            "test": {
                "name": "Test Job",
                "steps": [{"name": "Test Step", "run": "echo test"}],
            }
        },
    }
    with pytest.raises(ValidationError) as exc_info:
        Workflow(**workflow_dict)
    assert "install" in str(exc_info.value).lower()


def test_workflow_no_tools():
    """Test workflow without tools."""
    workflow_dict = {
        "name": "Test Workflow",
        "jobs": {
            "test": {
                "name": "Test Job",
                "steps": [{"name": "Test Step", "run": "echo test"}],
            }
        },
    }
    workflow = Workflow(**workflow_dict)
    assert workflow.tools is None
