"""Private photo storage on Supabase Storage (spec §9).

Image bytes never pass through this API. The app uploads and downloads directly
against a private bucket using short-lived signed URLs, which keeps large
transfers off the backend and means a compromised API still cannot read anyone's
photos without minting a URL first.

The spec names S3; Supabase Storage was chosen instead because the project
already exists and the model is identical — private bucket, signed URLs both
directions. See DECISIONS.md. This module is the entire difference: the router,
schemas and tests are storage-agnostic.
"""

import re
import uuid
from functools import lru_cache

import httpx
from fastapi import HTTPException, status

from app.core.certs import default_ssl_context
from app.core.config import get_settings

#: Spec §9 — what the bucket will accept.
ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/heic")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

UPLOAD_URL_TTL_SECONDS = 10 * 60
VIEW_URL_TTL_SECONDS = 60 * 60

#: Storage calls are small JSON round trips; a slow one should surface rather
#: than hold a request open.
REQUEST_TIMEOUT_SECONDS = 15.0

#: Supabase lists objects in pages.
LIST_PAGE_SIZE = 100


class StorageNotConfiguredError(RuntimeError):
    """Raised when photo endpoints are called before a bucket exists."""


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_storage_bucket and settings.supabase_service_key)


def require_configured() -> None:
    """Fail loudly and specifically rather than with an opaque 500."""
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Photo storage is not configured on this server",
        )


@lru_cache
def _client() -> httpx.Client:
    """One pooled client. The service key stays here and never leaves the API."""
    settings = get_settings()
    if not is_configured():
        raise StorageNotConfiguredError

    return httpx.Client(
        base_url=settings.storage_url,
        headers={
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "apikey": settings.supabase_service_key or "",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
        verify=default_ssl_context(),
    )


def _bucket() -> str:
    bucket = get_settings().supabase_storage_bucket
    if not bucket:
        raise StorageNotConfiguredError
    return bucket


def _absolute(path: str) -> str:
    """Supabase returns URLs relative to the storage root."""
    return f"{get_settings().storage_url}/{path.lstrip('/')}"


def _raise_for_status(response: httpx.Response, action: str) -> None:
    if response.is_success:
        return
    # Never surface the provider's response body — it can echo the key.
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Photo storage could not {action}",
    )


def list_buckets() -> list[str]:
    """Bucket names on the project. For diagnostics — the API never needs this."""
    response = _client().get("/bucket")
    _raise_for_status(response, "list buckets")
    return [bucket["name"] for bucket in response.json()]


#: Exactly what `build_key` emits: `{uuid4}/{uuid4}.jpg`, nothing else. Anchored
#: so no path separator, traversal segment or alternative extension can slip in.
_KEY_SHAPE = re.compile(r"[0-9a-f-]{36}/[0-9a-f-]{36}\.jpg")


def build_key(user_id: uuid.UUID) -> str:
    """`{user_id}/{uuid}.jpg` (spec §9).

    The user-id prefix is what makes account deletion a single prefix sweep, and
    keeps one user's objects trivially separable from another's.
    """
    return f"{user_id}/{uuid.uuid4()}.jpg"


def owns_key(user_id: uuid.UUID, key: str) -> bool:
    """Guard against a client claiming a key under someone else's prefix.

    Matches the exact shape `build_key` produces rather than testing the prefix.
    A prefix test accepts `{user_id}/../{someone_else}/photo.jpg`, which starts
    with the caller's prefix but does not stay under it — whether the storage
    backend resolves that `..` is its business, and not something this check
    should be relying on.
    """
    return _KEY_SHAPE.fullmatch(key) is not None and key.startswith(f"{user_id}/")


def presign_upload(key: str, content_type: str) -> str:
    """A short-lived upload URL the device can PUT straight to."""
    response = _client().post(f"/object/upload/sign/{_bucket()}/{key}")
    _raise_for_status(response, "issue an upload link")

    return _absolute(response.json()["url"])


def presign_view(key: str) -> str:
    """A one-hour download URL. Never cached to disk beyond its TTL (spec §9)."""
    response = _client().post(
        f"/object/sign/{_bucket()}/{key}", json={"expiresIn": VIEW_URL_TTL_SECONDS}
    )
    _raise_for_status(response, "issue a view link")

    return _absolute(response.json()["signedURL"])


def delete_object(key: str) -> None:
    response = _client().request("DELETE", f"/object/{_bucket()}", json={"prefixes": [key]})
    _raise_for_status(response, "delete the photo")


def delete_prefix(prefix: str) -> int:
    """Remove every object under a prefix, for account deletion (§10).

    Paged, because a long-standing user accumulates more objects than one list
    call returns and a partial purge would leave photos behind after the account
    they belong to is gone.
    """
    client = _client()
    bucket = _bucket()
    folder = prefix.rstrip("/")
    deleted = 0

    while True:
        listing = client.post(
            f"/object/list/{bucket}",
            json={"prefix": folder, "limit": LIST_PAGE_SIZE, "offset": 0},
        )
        _raise_for_status(listing, "list your photos")

        names = [item["name"] for item in listing.json() if item.get("name")]
        if not names:
            return deleted

        removal = client.request(
            "DELETE",
            f"/object/{bucket}",
            json={"prefixes": [f"{folder}/{name}" for name in names]},
        )
        _raise_for_status(removal, "delete your photos")
        deleted += len(names)

        # A short page means the folder is now empty.
        if len(names) < LIST_PAGE_SIZE:
            return deleted
