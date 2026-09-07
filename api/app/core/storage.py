"""S3 access for progress photos (spec §9).

Image bytes never pass through this API. The app uploads and downloads directly
against a private bucket using short-lived presigned URLs, which keeps large
uploads off the backend entirely and means a compromised API still cannot read
anyone's photos without minting a URL.
"""

import uuid
from functools import lru_cache

import boto3
from botocore.config import Config
from fastapi import HTTPException, status

from app.core.config import get_settings

#: Spec §9 — what the bucket will accept.
ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/heic")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

UPLOAD_URL_TTL_SECONDS = 10 * 60
VIEW_URL_TTL_SECONDS = 60 * 60


class StorageNotConfiguredError(RuntimeError):
    """Raised when photo endpoints are called before a bucket exists."""


@lru_cache
def _client():
    settings = get_settings()
    if not settings.s3_bucket or not settings.aws_region:
        raise StorageNotConfiguredError
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        # SigV4 is required for presigned URLs to work in every region.
        config=Config(signature_version="s3v4"),
    )


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.s3_bucket and settings.aws_region)


def require_configured() -> None:
    """Fail loudly and specifically rather than with an opaque 500."""
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Photo storage is not configured on this server",
        )


def build_key(user_id: uuid.UUID) -> str:
    """`{user_id}/{uuid}.jpg` (spec §9).

    The user id prefix is what makes deletion a single prefix sweep, and keeps
    one user's objects trivially separable from another's.
    """
    return f"{user_id}/{uuid.uuid4()}.jpg"


def owns_key(user_id: uuid.UUID, key: str) -> bool:
    """Guard against a client claiming a key under someone else's prefix."""
    return key.startswith(f"{user_id}/")


def presign_upload(key: str, content_type: str) -> str:
    """A short-lived PUT URL, pinned to the content type it was issued for."""
    settings = get_settings()
    return _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=UPLOAD_URL_TTL_SECONDS,
    )


def presign_view(key: str) -> str:
    """A one-hour GET URL. Never cached to disk beyond its TTL (spec §9)."""
    settings = get_settings()
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=VIEW_URL_TTL_SECONDS,
    )


def delete_object(key: str) -> None:
    settings = get_settings()
    _client().delete_object(Bucket=settings.s3_bucket, Key=key)


def delete_prefix(prefix: str) -> int:
    """Remove every object under a prefix, for account deletion (§10).

    Paginated because a long-standing user can accumulate more objects than a
    single list call returns, and a partial purge would leave photos behind
    after the account they belong to is gone.
    """
    settings = get_settings()
    client = _client()
    deleted = 0

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
        contents = page.get("Contents", [])
        if not contents:
            continue
        client.delete_objects(
            Bucket=settings.s3_bucket,
            Delete={"Objects": [{"Key": item["Key"]} for item in contents]},
        )
        deleted += len(contents)

    return deleted
