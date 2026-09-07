"""`/photos` (spec §6, §9) and account deletion (§10, §13).

S3 is stubbed: these assert our own rules — ownership, idempotency, ordering
and the cascade — not that boto3 works.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import storage
from app.models import DailyLog, Goal, Photo, Profile, WorkoutSession
from tests.conftest import make_token


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> dict:
    """A pretend bucket that records what was asked of it."""
    state: dict = {"deleted": [], "prefixes": [], "objects": set()}

    monkeypatch.setattr(storage, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "require_configured", lambda: None)
    monkeypatch.setattr(
        storage, "presign_upload", lambda key, ct: f"https://bucket.test/{key}?upload&ct={ct}"
    )
    monkeypatch.setattr(storage, "presign_view", lambda key: f"https://bucket.test/{key}?view")
    monkeypatch.setattr(storage, "delete_object", lambda key: state["deleted"].append(key))

    def delete_prefix(prefix: str) -> int:
        state["prefixes"].append(prefix)
        return 3

    monkeypatch.setattr(storage, "delete_prefix", delete_prefix)
    return state


def presign(client: TestClient, headers: dict[str, str], content_type: str = "image/jpeg"):
    return client.post("/photos/presign", json={"content_type": content_type}, headers=headers)


# --- presign ---------------------------------------------------------------


def test_requires_authentication(client: TestClient, s3: dict) -> None:
    assert client.post("/photos/presign", json={"content_type": "image/jpeg"}).status_code == 401


def test_presign_returns_a_url_and_a_key(
    client: TestClient, auth_headers: dict[str, str], user_id: uuid.UUID, s3: dict
) -> None:
    body = presign(client, auth_headers).json()

    assert body["s3_key"].startswith(f"{user_id}/")
    assert body["s3_key"].endswith(".jpg")
    assert "upload" in body["upload_url"]


def test_the_key_is_minted_by_the_server(
    client: TestClient, auth_headers: dict[str, str], user_id: uuid.UUID, s3: dict
) -> None:
    """A client that could choose its own key could aim at another user."""
    first = presign(client, auth_headers).json()["s3_key"]
    second = presign(client, auth_headers).json()["s3_key"]

    assert first != second
    assert all(k.startswith(f"{user_id}/") for k in (first, second))


def test_unsupported_content_types_are_refused(
    client: TestClient, auth_headers: dict[str, str], s3: dict
) -> None:
    assert presign(client, auth_headers, "image/gif").status_code == 422
    assert presign(client, auth_headers, "application/pdf").status_code == 422


def test_photo_endpoints_say_so_when_storage_is_absent(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """No bucket configured yet — a specific 503 beats an opaque 500."""
    resp = presign(client, auth_headers)
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


# --- confirm ---------------------------------------------------------------


def test_confirming_records_the_photo(
    client: TestClient, auth_headers: dict[str, str], s3: dict
) -> None:
    key = presign(client, auth_headers).json()["s3_key"]
    resp = client.post(
        "/photos", json={"s3_key": key, "taken_on": "2026-09-07"}, headers=auth_headers
    )

    assert resp.status_code == 201
    assert resp.json()["taken_on"] == "2026-09-07"
    assert "view" in resp.json()["view_url"]


def test_confirming_twice_does_not_duplicate(
    client: TestClient, auth_headers: dict[str, str], s3: dict
) -> None:
    """The confirm call is queued (§8), so a retry must be harmless."""
    key = presign(client, auth_headers).json()["s3_key"]
    payload = {"s3_key": key, "taken_on": "2026-09-07"}

    first = client.post("/photos", json=payload, headers=auth_headers).json()
    again = client.post("/photos", json=payload, headers=auth_headers).json()

    assert first["id"] == again["id"]
    listed = client.get("/photos", params={"year": 2026, "month": 9}, headers=auth_headers).json()
    assert len(listed) == 1


def test_a_key_under_someone_elses_prefix_is_refused(
    client: TestClient, auth_headers: dict[str, str], s3: dict
) -> None:
    stranger_key = f"{uuid.uuid4()}/{uuid.uuid4()}.jpg"
    resp = client.post(
        "/photos", json={"s3_key": stranger_key, "taken_on": "2026-09-07"}, headers=auth_headers
    )
    assert resp.status_code == 403


# --- listing ---------------------------------------------------------------


def test_listing_is_scoped_to_the_month_and_newest_first(
    client: TestClient, auth_headers: dict[str, str], s3: dict
) -> None:
    for day in ("2026-08-31", "2026-09-01", "2026-09-20", "2026-10-01"):
        key = presign(client, auth_headers).json()["s3_key"]
        client.post("/photos", json={"s3_key": key, "taken_on": day}, headers=auth_headers)

    listed = client.get("/photos", params={"year": 2026, "month": 9}, headers=auth_headers).json()
    assert [p["taken_on"] for p in listed] == ["2026-09-20", "2026-09-01"]


def test_december_rolls_into_the_next_year(
    client: TestClient, auth_headers: dict[str, str], s3: dict
) -> None:
    """The month window is built by hand; the December edge is where it breaks."""
    for day in ("2026-12-31", "2027-01-01"):
        key = presign(client, auth_headers).json()["s3_key"]
        client.post("/photos", json={"s3_key": key, "taken_on": day}, headers=auth_headers)

    listed = client.get("/photos", params={"year": 2026, "month": 12}, headers=auth_headers).json()
    assert [p["taken_on"] for p in listed] == ["2026-12-31"]


def test_photos_are_private(client: TestClient, auth_headers: dict[str, str], s3: dict) -> None:
    key = presign(client, auth_headers).json()["s3_key"]
    client.post("/photos", json={"s3_key": key, "taken_on": "2026-09-07"}, headers=auth_headers)

    other = {"Authorization": f"Bearer {make_token()}"}
    assert client.get("/photos", params={"year": 2026, "month": 9}, headers=other).json() == []


# --- deleting one photo ----------------------------------------------------


def test_deleting_removes_the_row_and_the_object(
    client: TestClient, auth_headers: dict[str, str], s3: dict
) -> None:
    key = presign(client, auth_headers).json()["s3_key"]
    photo_id = client.post(
        "/photos", json={"s3_key": key, "taken_on": "2026-09-07"}, headers=auth_headers
    ).json()["id"]

    assert client.delete(f"/photos/{photo_id}", headers=auth_headers).status_code == 204
    assert key in s3["deleted"]
    assert (
        client.get("/photos", params={"year": 2026, "month": 9}, headers=auth_headers).json() == []
    )


def test_deleting_another_users_photo_is_a_404(
    client: TestClient, auth_headers: dict[str, str], s3: dict
) -> None:
    key = presign(client, auth_headers).json()["s3_key"]
    photo_id = client.post(
        "/photos", json={"s3_key": key, "taken_on": "2026-09-07"}, headers=auth_headers
    ).json()["id"]

    other = {"Authorization": f"Bearer {make_token()}"}
    assert client.delete(f"/photos/{photo_id}", headers=other).status_code == 404
    assert s3["deleted"] == []


# --- account deletion (§10, §13) -------------------------------------------


def test_deletion_needs_the_confirmation_phrase(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert (
        client.post("/account/delete", json={"confirm": "yes"}, headers=auth_headers).status_code
        == 422
    )
    assert (
        client.post("/account/delete", json={"confirm": ""}, headers=auth_headers).status_code
        == 422
    )


def test_deletion_removes_everything_the_user_owns(
    client: TestClient,
    db: Session,
    auth_headers: dict[str, str],
    user_id: uuid.UUID,
    shared_exercise: int,
    s3: dict,
) -> None:
    """App Store review requires this to delete, not deactivate (§13)."""
    client.put("/daily-logs/2026-09-07", json={"weight_kg": 90.0}, headers=auth_headers)
    client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)
    client.post(
        "/workout-sessions",
        json={
            "client_uuid": str(uuid.uuid4()),
            "session_date": "2026-09-07",
            "split": "push",
            "sets": [
                {"exercise_id": shared_exercise, "set_number": 1, "weight_kg": 100, "reps": 5}
            ],
        },
        headers=auth_headers,
    )
    key = presign(client, auth_headers).json()["s3_key"]
    client.post("/photos", json={"s3_key": key, "taken_on": "2026-09-07"}, headers=auth_headers)

    resp = client.post("/account/delete", json={"confirm": "DELETE"}, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["deleted_photos"] == 3
    assert resp.json()["supabase_user_pending"] is True
    assert s3["prefixes"] == [f"{user_id}/"]

    # Everything cascades from profiles (§5).
    assert db.get(Profile, user_id) is None
    assert db.scalars(select(DailyLog).where(DailyLog.user_id == user_id)).all() == []
    assert db.scalars(select(Goal).where(Goal.user_id == user_id)).all() == []
    assert db.scalars(select(WorkoutSession).where(WorkoutSession.user_id == user_id)).all() == []
    assert db.scalars(select(Photo).where(Photo.user_id == user_id)).all() == []


def test_deletion_leaves_other_users_alone(
    client: TestClient, db: Session, auth_headers: dict[str, str], s3: dict
) -> None:
    keeper_token = make_token()
    keeper = {"Authorization": f"Bearer {keeper_token}"}
    client.put("/daily-logs/2026-09-07", json={"weight_kg": 88.0}, headers=keeper)
    client.put("/daily-logs/2026-09-07", json={"weight_kg": 90.0}, headers=auth_headers)

    client.post("/account/delete", json={"confirm": "DELETE"}, headers=auth_headers)

    remaining = client.get(
        "/daily-logs", params={"from": "2026-09-01", "to": "2026-09-30"}, headers=keeper
    ).json()
    assert len(remaining) == 1


def test_deletion_works_without_storage_configured(
    client: TestClient, auth_headers: dict[str, str], user_id: uuid.UUID, db: Session
) -> None:
    """A user must be able to delete their account before photos exist."""
    client.put("/daily-logs/2026-09-07", json={"weight_kg": 90.0}, headers=auth_headers)

    resp = client.post("/account/delete", json={"confirm": "DELETE"}, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["deleted_photos"] == 0
    assert db.get(Profile, user_id) is None
