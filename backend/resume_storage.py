"""Cloudflare R2 storage for user resume objects."""

from __future__ import annotations

import mimetypes
import logging
import re
from uuid import uuid4

from . import config

logger = logging.getLogger(__name__)


def _client():
    if not all((config.R2_ACCOUNT_ID, config.R2_ACCESS_KEY_ID, config.R2_SECRET_ACCESS_KEY, config.R2_OBJECT_BUCKET)):
        raise RuntimeError("Resume storage is not configured. Set the R2_* environment variables.")
    import boto3

    endpoint = config.R2_ENDPOINT_URL or f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def save_resume(user_id: int, filename: str, data: bytes) -> tuple[str, str | None]:
    safe_filename = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip(".-") or "resume.txt"
    object_key = f"users/{user_id}/resumes/{uuid4().hex}-{safe_filename}"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    _client().put_object(
        Bucket=config.R2_OBJECT_BUCKET,
        Key=object_key,
        Body=data,
        ContentType=content_type,
    )
    logger.info("Stored resume in R2 bucket=%s key=%s bytes=%d", config.R2_OBJECT_BUCKET, object_key, len(data))
    return object_key, None


def load_resume(object_key: str, object_version_id: str | None) -> bytes:
    request = {"Bucket": config.R2_OBJECT_BUCKET, "Key": object_key}
    if object_version_id:
        request["VersionId"] = object_version_id
    response = _client().get_object(**request)
    data = response["Body"].read()
    logger.info("Loaded resume from R2 bucket=%s key=%s bytes=%d", config.R2_OBJECT_BUCKET, object_key, len(data))
    return data