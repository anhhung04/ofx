"""S3 utilities for OFX framework."""

import tempfile
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

from ofx.settings import ALLOWED_WORKFLOW_FILE_EXTENSIONS


def download_s3_workflow(s3_uri: str) -> tuple[Path, str]:
    """Download workflow from S3.

    Args:
        s3_uri: S3 URI in format s3://bucket/path/to/workflow.yml

    Returns:
        Tuple of (local_path, content)

    Raises:
        RuntimeError: If S3 download fails
    """
    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3":
        raise ValueError(f"Invalid S3 URI: {s3_uri}")

    bucket = parsed.netloc
    key = parsed.path.lstrip("/")

    if not key:
        raise ValueError(f"S3 URI must include a key path: {s3_uri}")

    key_path = Path(key)
    if key_path.suffix not in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
        original_key = key
        found = False
        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            test_key = str(key_path.with_suffix(ext))
            try:
                s3 = boto3.client("s3")
                s3.head_object(Bucket=bucket, Key=test_key)
                key = test_key
                found = True
                break
            except ClientError:
                continue

        if not found:
            raise RuntimeError(
                f"No workflow found at s3://{bucket}/{original_key} with extensions {ALLOWED_WORKFLOW_FILE_EXTENSIONS}"
            )

    try:
        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8")

        tmp_dir = Path(tempfile.mkdtemp(prefix=".ofx_s3_"))
        workflow_file = tmp_dir / Path(key).name
        workflow_file.write_text(content)

        return workflow_file, content

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "NoSuchBucket":
            raise RuntimeError(f"S3 bucket not found: {bucket}") from e
        elif error_code == "NoSuchKey":
            raise RuntimeError(f"Workflow not found: s3://{bucket}/{key}") from e
        elif error_code in ["AccessDenied", "InvalidAccessKeyId"]:
            raise RuntimeError(
                "Access denied to S3. Check AWS credentials and bucket permissions."
            ) from e
        else:
            raise RuntimeError(f"Failed to download from S3: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to download workflow from S3: {e}") from e
