"""Test S3 workflow resolution functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 S3 client."""
    with patch("boto3.client") as mock_client:
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3
        yield mock_s3


def test_is_s3_path():
    """Test S3 path detection."""
    from ofx.utils.path import is_s3_path

    assert is_s3_path("s3://bucket/path/to/workflow.yml") is True
    assert is_s3_path("s3://my-bucket/workflows/test.yaml") is True
    assert is_s3_path("https://example.com/workflow.yml") is False
    assert is_s3_path("http://example.com/workflow.yml") is False
    assert is_s3_path("/local/path/workflow.yml") is False
    assert is_s3_path("workflow.yml") is False


def test_download_s3_workflow_success(mock_boto3_client):
    """Test successful S3 workflow download."""
    from ofx.utils.s3 import download_s3_workflow

    workflow_content = """
name: Test Workflow
jobs:
  test:
    steps:
      - run: echo "test"
"""

    # Mock S3 response
    mock_response = {
        "Body": MagicMock(read=MagicMock(return_value=workflow_content.encode("utf-8")))
    }
    mock_boto3_client.get_object.return_value = mock_response

    # Test download
    flow_path, content = download_s3_workflow("s3://my-bucket/workflows/test.yml")

    # Verify
    assert content == workflow_content
    assert flow_path.exists()
    assert flow_path.name == "test.yml"
    mock_boto3_client.get_object.assert_called_once_with(
        Bucket="my-bucket", Key="workflows/test.yml"
    )


def test_download_s3_workflow_with_extension_detection(mock_boto3_client):
    """Test S3 workflow download with automatic extension detection."""
    from ofx.utils.s3 import download_s3_workflow

    workflow_content = "name: Test\njobs: {}"

    # Mock head_object to return valid response for .yml extension
    mock_boto3_client.head_object.return_value = {}
    mock_response = {
        "Body": MagicMock(read=MagicMock(return_value=workflow_content.encode("utf-8")))
    }
    mock_boto3_client.get_object.return_value = mock_response

    # Test with path without extension
    flow_path, content = download_s3_workflow("s3://my-bucket/workflows/test")

    # Should have tried to detect extension
    assert mock_boto3_client.head_object.called
    assert content == workflow_content


def test_download_s3_workflow_bucket_not_found(mock_boto3_client):
    """Test S3 workflow download with non-existent bucket."""
    from botocore.exceptions import ClientError

    from ofx.utils.s3 import download_s3_workflow

    # Mock NoSuchBucket error
    error_response = {"Error": {"Code": "NoSuchBucket"}}
    mock_boto3_client.get_object.side_effect = ClientError(error_response, "GetObject")

    with pytest.raises(RuntimeError, match="S3 bucket not found"):
        download_s3_workflow("s3://nonexistent-bucket/workflow.yml")


def test_download_s3_workflow_key_not_found(mock_boto3_client):
    """Test S3 workflow download with non-existent key."""
    from botocore.exceptions import ClientError

    from ofx.utils.s3 import download_s3_workflow

    # Mock NoSuchKey error
    error_response = {"Error": {"Code": "NoSuchKey"}}
    mock_boto3_client.get_object.side_effect = ClientError(error_response, "GetObject")

    with pytest.raises(RuntimeError, match="Workflow not found"):
        download_s3_workflow("s3://my-bucket/nonexistent.yml")


def test_download_s3_workflow_access_denied(mock_boto3_client):
    """Test S3 workflow download with access denied."""
    from botocore.exceptions import ClientError

    from ofx.utils.s3 import download_s3_workflow

    # Mock AccessDenied error
    error_response = {"Error": {"Code": "AccessDenied"}}
    mock_boto3_client.get_object.side_effect = ClientError(error_response, "GetObject")

    with pytest.raises(RuntimeError, match="Access denied to S3"):
        download_s3_workflow("s3://restricted-bucket/workflow.yml")


def test_download_s3_workflow_invalid_uri():
    """Test S3 workflow download with invalid URI."""
    from ofx.utils.s3 import download_s3_workflow

    with pytest.raises(ValueError, match="Invalid S3 URI"):
        download_s3_workflow("http://example.com/workflow.yml")

    with pytest.raises(ValueError, match="S3 URI must include a key path"):
        download_s3_workflow("s3://bucket-only")


@patch("ofx.utils.workflow_utils.download_s3_workflow")
def test_find_workflow_from_s3(mock_download, tmp_path):
    """Test finding workflow from S3 URI."""
    from ofx.utils.workflow_utils import find_workflow

    # Clear the cache to ensure fresh call
    find_workflow.cache_clear()

    workflow_content = """
name: S3 Test Workflow
description: Test workflow from S3
jobs:
  test_job:
    steps:
      - run: echo "Hello from S3"
"""

    # Create temporary workflow file
    workflow_file = tmp_path / "test.yml"
    workflow_file.write_text(workflow_content)

    # Mock download to return the temp file
    mock_download.return_value = (workflow_file, workflow_content)

    # Test finding S3 workflow
    flow_path, workflow = find_workflow("s3://my-bucket/workflows/test.yml", tuple())

    # Verify
    assert workflow.name == "S3 Test Workflow"
    assert workflow.description == "Test workflow from S3"
    assert "test_job" in workflow.jobs
    mock_download.assert_called_once_with("s3://my-bucket/workflows/test.yml")


def test_s3_workflow_integration():
    """Integration test for S3 workflow paths in workflow context."""
    from ofx.utils.path import is_s3_path

    # Test various S3 URI formats
    test_cases = [
        ("s3://bucket/workflow.yml", True),
        ("s3://bucket/path/to/workflow.yaml", True),
        ("s3://my-workflows/prod/main.yml", True),
        ("S3://bucket/workflow.yml", False),  # Case sensitive
        ("s3:///workflow.yml", True),  # No bucket is technically valid URI
    ]

    for uri, expected in test_cases:
        result = is_s3_path(uri)
        assert result == expected, f"Expected {uri} to be {expected}, got {result}"
