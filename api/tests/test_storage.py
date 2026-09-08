"""app/core/storage.py — URL construction, paging and failure handling.

Supabase is mocked at the HTTP layer rather than the function layer, so the
requests we actually send are what gets asserted.
"""

import uuid

import httpx
import pytest
from fastapi import HTTPException

from app.core import storage

BUCKET = "photos"
STORAGE_ROOT = "https://project.supabase.co/storage/v1"


@pytest.fixture
def supabase(monkeypatch: pytest.MonkeyPatch):
    """A fake Storage API that records the calls made to it."""
    calls: list[httpx.Request] = []
    state: dict = {"objects": [], "fail": None}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path

        if state["fail"] is not None:
            return httpx.Response(state["fail"], json={"error": "nope"})

        if "/object/upload/sign/" in path:
            key = path.split(f"/object/upload/sign/{BUCKET}/", 1)[1]
            return httpx.Response(200, json={"url": f"object/upload/sign/{BUCKET}/{key}?token=abc"})
        if "/object/sign/" in path:
            key = path.split(f"/object/sign/{BUCKET}/", 1)[1]
            return httpx.Response(200, json={"signedURL": f"/object/sign/{BUCKET}/{key}?token=xyz"})
        if f"/object/list/{BUCKET}" in path:
            page = state["objects"][:100]
            state["objects"] = state["objects"][100:]
            return httpx.Response(200, json=[{"name": n} for n in page])
        if path.endswith(f"/object/{BUCKET}") and request.method == "DELETE":
            return httpx.Response(200, json={})

        return httpx.Response(404, json={})

    client = httpx.Client(
        base_url=STORAGE_ROOT,
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer service-key"},
    )

    monkeypatch.setattr(storage, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "_client", lambda: client)
    monkeypatch.setattr(storage, "_bucket", lambda: BUCKET)
    monkeypatch.setattr(storage, "_absolute", lambda path: f"{STORAGE_ROOT}/{path.lstrip('/')}")

    return {"calls": calls, "state": state}


# --- keys ------------------------------------------------------------------


def test_keys_are_namespaced_by_user() -> None:
    user_id = uuid.uuid4()
    key = storage.build_key(user_id)

    assert key.startswith(f"{user_id}/")
    assert key.endswith(".jpg")


def test_keys_are_unique() -> None:
    user_id = uuid.uuid4()
    assert storage.build_key(user_id) != storage.build_key(user_id)


def test_ownership_is_decided_by_the_prefix() -> None:
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    key = storage.build_key(mine)

    assert storage.owns_key(mine, key) is True
    assert storage.owns_key(theirs, key) is False


def test_a_lookalike_prefix_is_not_ownership() -> None:
    """`abc/` must not match a key under `abcdef/`."""
    user_id = uuid.uuid4()
    assert storage.owns_key(user_id, f"{user_id}extra/photo.jpg") is False


def test_traversal_out_of_the_prefix_is_not_ownership() -> None:
    """A key may not climb out of the prefix it appears to be under.

    `{mine}/../{theirs}/x.jpg` starts with `{mine}/`, so a prefix test accepts
    it. Whether the storage backend then resolves the `..` is its business, not
    something this check should be betting on.
    """
    mine, theirs = uuid.uuid4(), uuid.uuid4()

    assert storage.owns_key(mine, f"{mine}/../{theirs}/photo.jpg") is False
    assert storage.owns_key(mine, f"{mine}/..%2f{theirs}/photo.jpg") is False
    assert storage.owns_key(mine, f"{mine}/sub/dir/photo.jpg") is False


def test_only_the_shape_build_key_produces_is_accepted() -> None:
    """Anything that is not exactly `{user_id}/{uuid4}.jpg` is rejected."""
    user_id = uuid.uuid4()

    assert storage.owns_key(user_id, storage.build_key(user_id)) is True
    assert storage.owns_key(user_id, f"{user_id}/photo.png") is False
    assert storage.owns_key(user_id, f"{user_id}/not-a-uuid.jpg") is False
    assert storage.owns_key(user_id, f"{user_id}/") is False


# --- signed URLs -----------------------------------------------------------


def test_upload_urls_are_absolute(supabase: dict) -> None:
    url = storage.presign_upload("user/photo.jpg", "image/jpeg")

    assert url.startswith(STORAGE_ROOT)
    assert "token=abc" in url


def test_view_urls_are_absolute(supabase: dict) -> None:
    url = storage.presign_view("user/photo.jpg")

    assert url.startswith(STORAGE_ROOT)
    assert "token=xyz" in url


def test_view_urls_request_the_specified_lifetime(supabase: dict) -> None:
    storage.presign_view("user/photo.jpg")

    import json

    body = json.loads(supabase["calls"][-1].content)
    assert body["expiresIn"] == storage.VIEW_URL_TTL_SECONDS


# --- deletion --------------------------------------------------------------


def test_deleting_one_object(supabase: dict) -> None:
    storage.delete_object("user/photo.jpg")

    request = supabase["calls"][-1]
    assert request.method == "DELETE"
    assert b"user/photo.jpg" in request.content


def test_deleting_a_prefix_removes_every_object(supabase: dict) -> None:
    supabase["state"]["objects"] = [f"photo-{i}.jpg" for i in range(5)]

    assert storage.delete_prefix("user-id/") == 5


def test_deleting_a_prefix_pages_through_large_folders(supabase: dict) -> None:
    """A partial purge would leave photos behind after the account is gone."""
    supabase["state"]["objects"] = [f"photo-{i}.jpg" for i in range(250)]

    assert storage.delete_prefix("user-id/") == 250


def test_deleting_an_empty_prefix_is_fine(supabase: dict) -> None:
    assert storage.delete_prefix("user-id/") == 0


def test_prefix_deletion_sends_full_paths(supabase: dict) -> None:
    supabase["state"]["objects"] = ["photo.jpg"]
    storage.delete_prefix("user-id/")

    deletion = [c for c in supabase["calls"] if c.method == "DELETE"][-1]
    assert b"user-id/photo.jpg" in deletion.content


# --- failure handling ------------------------------------------------------


def test_a_provider_failure_becomes_a_502(supabase: dict) -> None:
    supabase["state"]["fail"] = 500

    with pytest.raises(HTTPException) as raised:
        storage.presign_view("user/photo.jpg")

    assert raised.value.status_code == 502


def test_failures_never_echo_the_provider_response(supabase: dict) -> None:
    """That body can contain the service key; it must not reach a client."""
    supabase["state"]["fail"] = 403

    with pytest.raises(HTTPException) as raised:
        storage.presign_upload("user/photo.jpg", "image/jpeg")

    assert "nope" not in str(raised.value.detail)
    assert "service" not in str(raised.value.detail).lower()


def test_unconfigured_storage_reports_503() -> None:
    with pytest.raises(HTTPException) as raised:
        storage.require_configured()

    assert raised.value.status_code == 503
    assert "not configured" in raised.value.detail
