"""Cross-user access, attempted deliberately.

Every other test file checks that a user can reach their own data. This one
checks that they cannot reach anyone else's — the failure mode that matters
once more than one person has an account, and the one that silent success
hides. Each test is written as an attack: it does the thing that must not work
and asserts it did not.

Two users exist throughout: `owner`, who has data, and `attacker`, who is a
perfectly legitimate signed-in user trying to reach it.
"""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyLog, Goal, Photo, WorkoutSession
from tests.conftest import make_token

DAY = "2026-09-07"
TODAY = {"date": "2026-09-30"}


@pytest.fixture
def owner_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def owner(owner_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(owner_id)}"}


@pytest.fixture
def attacker_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def attacker(attacker_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(attacker_id)}"}


@pytest.fixture
def owners_data(client: TestClient, owner: dict[str, str], shared_exercise: int) -> dict:
    """Give the owner one of everything worth stealing."""
    client.put(f"/daily-logs/{DAY}", json={"weight_kg": 90.0, "calories": 2400}, headers=owner)
    goal = client.post("/goals", json={"goal_weight_kg": 80}, headers=owner).json()

    session = client.post(
        "/workout-sessions",
        json={
            "client_uuid": str(uuid.uuid4()),
            "session_date": DAY,
            "split": "push",
            "sets": [
                {"exercise_id": shared_exercise, "set_number": 1, "weight_kg": 100, "reps": 5}
            ],
        },
        headers=owner,
    ).json()

    custom = client.post(
        "/exercises", json={"name": "Owners Secret Lift", "muscle_group": "chest"}, headers=owner
    ).json()

    return {"goal": goal, "session": session["session"], "exercise": custom}


# --- reading someone else's data -------------------------------------------


def test_cannot_read_another_users_daily_logs(
    client: TestClient, attacker: dict[str, str], owners_data: dict
) -> None:
    listed = client.get(
        "/daily-logs", params={"from": "2026-09-01", "to": "2026-09-30"}, headers=attacker
    ).json()
    assert listed == []


def test_cannot_read_another_users_goal(
    client: TestClient, attacker: dict[str, str], owners_data: dict
) -> None:
    assert client.get("/goals/active", headers=attacker).status_code == 404


def test_cannot_read_another_users_sessions(
    client: TestClient, attacker: dict[str, str], owners_data: dict
) -> None:
    listed = client.get(
        "/workout-sessions", params={"from": "2026-09-01", "to": "2026-09-30"}, headers=attacker
    ).json()
    assert listed == []


def test_cannot_see_another_users_custom_exercise(
    client: TestClient, attacker: dict[str, str], owners_data: dict
) -> None:
    found = client.get("/exercises", params={"q": "secret"}, headers=attacker).json()
    assert found == []


def test_cannot_read_another_users_last_sets(
    client: TestClient, attacker: dict[str, str], owners_data: dict
) -> None:
    """Even naming the exercise id directly must not reveal their numbers."""
    exercise_id = owners_data["exercise"]["id"]
    assert client.get(f"/exercises/{exercise_id}/last-sets", headers=attacker).status_code == 404


def test_another_users_dashboard_is_empty(
    client: TestClient, attacker: dict[str, str], owners_data: dict
) -> None:
    body = client.get("/dashboard", params=TODAY, headers=attacker).json()

    assert body["weight"]["series"] == []
    assert body["goal"] is None
    assert body["streaks"] == {"logged_14": 0, "trained_14": 0}
    assert body["prs_recent"] == []
    assert body["recap"] is None
    assert all(r["sets_this_week"] == 0 for r in body["volume"])


def test_cannot_read_another_users_photos(
    client: TestClient, attacker: dict[str, str], owner: dict[str, str], s3_stub: dict
) -> None:
    key = client.post("/photos/presign", json={"content_type": "image/jpeg"}, headers=owner).json()[
        "s3_key"
    ]
    client.post("/photos", json={"s3_key": key, "taken_on": DAY}, headers=owner)

    assert client.get("/photos", params={"year": 2026, "month": 9}, headers=attacker).json() == []


# --- writing to someone else's data ----------------------------------------


def test_writing_a_daily_log_cannot_touch_another_users_row(
    client: TestClient,
    db: Session,
    attacker: dict[str, str],
    owner_id: uuid.UUID,
    owners_data: dict,
) -> None:
    """The same date for two users must be two rows, not one shared one."""
    client.put(f"/daily-logs/{DAY}", json={"weight_kg": 60.0}, headers=attacker)

    owners_row = db.scalar(
        select(DailyLog).where(
            DailyLog.user_id == owner_id, DailyLog.log_date == date.fromisoformat(DAY)
        )
    )
    assert owners_row is not None
    assert float(owners_row.weight_kg) == 90.0


def test_cannot_edit_another_users_goal(
    client: TestClient, db: Session, attacker: dict[str, str], owners_data: dict
) -> None:
    """PATCH targets 'the active goal', which must mean the caller's own."""
    assert (
        client.patch("/goals/active", json={"goal_weight_kg": 40}, headers=attacker).status_code
        == 404
    )

    goal = db.get(Goal, owners_data["goal"]["id"])
    assert float(goal.goal_weight_kg) == 80.0


def test_creating_a_goal_does_not_close_another_users(
    client: TestClient, db: Session, attacker: dict[str, str], owners_data: dict
) -> None:
    client.put(f"/daily-logs/{DAY}", json={"weight_kg": 70.0}, headers=attacker)
    client.post("/goals", json={"goal_weight_kg": 65}, headers=attacker)

    assert db.get(Goal, owners_data["goal"]["id"]).status == "active"


def test_cannot_hijack_another_users_session_via_client_uuid(
    client: TestClient, attacker: dict[str, str], owners_data: dict, shared_exercise: int
) -> None:
    """Replaying someone's idempotency key must not return their session."""
    resp = client.post(
        "/workout-sessions",
        json={
            "client_uuid": owners_data["session"]["client_uuid"],
            "session_date": DAY,
            "split": "pull",
            "sets": [],
        },
        headers=attacker,
    )
    # 404, not 403: a 403 confirms the identifier is in use by someone, which is
    # the enumeration signal the status code is supposed to withhold.
    assert resp.status_code == 404
    assert "session" not in resp.json()


def test_cannot_log_sets_against_another_users_custom_exercise(
    client: TestClient, attacker: dict[str, str], owners_data: dict
) -> None:
    resp = client.post(
        "/workout-sessions",
        json={
            "client_uuid": str(uuid.uuid4()),
            "session_date": DAY,
            "split": "push",
            "sets": [
                {
                    "exercise_id": owners_data["exercise"]["id"],
                    "set_number": 1,
                    "weight_kg": 100,
                    "reps": 5,
                }
            ],
        },
        headers=attacker,
    )
    assert resp.status_code == 422


def test_cannot_claim_a_photo_key_under_another_users_prefix(
    client: TestClient, attacker: dict[str, str], owner_id: uuid.UUID, s3_stub: dict
) -> None:
    stolen = f"{owner_id}/{uuid.uuid4()}.jpg"
    resp = client.post("/photos", json={"s3_key": stolen, "taken_on": DAY}, headers=attacker)
    # 404, not 403 — see the note on session hijacking above.
    assert resp.status_code == 404


# --- deleting someone else's data ------------------------------------------


def test_cannot_delete_another_users_photo(
    client: TestClient,
    db: Session,
    attacker: dict[str, str],
    owner: dict[str, str],
    s3_stub: dict,
) -> None:
    key = client.post("/photos/presign", json={"content_type": "image/jpeg"}, headers=owner).json()[
        "s3_key"
    ]
    photo_id = client.post("/photos", json={"s3_key": key, "taken_on": DAY}, headers=owner).json()[
        "id"
    ]

    assert client.delete(f"/photos/{photo_id}", headers=attacker).status_code == 404
    assert db.get(Photo, photo_id) is not None
    assert s3_stub["deleted"] == []


def test_deleting_an_account_leaves_other_accounts_intact(
    client: TestClient,
    db: Session,
    attacker: dict[str, str],
    owner_id: uuid.UUID,
    owners_data: dict,
) -> None:
    client.put(f"/daily-logs/{DAY}", json={"weight_kg": 70.0}, headers=attacker)
    assert (
        client.post("/account/delete", json={"confirm": "DELETE"}, headers=attacker).status_code
        == 200
    )

    assert db.scalar(select(DailyLog).where(DailyLog.user_id == owner_id)) is not None
    assert db.get(Goal, owners_data["goal"]["id"]) is not None
    assert db.get(WorkoutSession, owners_data["session"]["id"]) is not None


# --- the admin surface -----------------------------------------------------


def test_a_normal_user_cannot_read_metrics(
    client: TestClient, attacker: dict[str, str], owners_data: dict
) -> None:
    assert client.get("/admin/metrics", params=TODAY, headers=attacker).status_code == 404


def test_metrics_are_not_reachable_by_guessing_the_path(
    client: TestClient, attacker: dict[str, str]
) -> None:
    for path in ("/admin/metrics/", "/Admin/Metrics", "/admin//metrics"):
        assert client.get(path, params=TODAY, headers=attacker).status_code in (307, 404)


# --- forged and malformed identities ---------------------------------------


def test_a_token_naming_another_user_must_be_signed_correctly(
    client: TestClient, owner_id: uuid.UUID, owners_data: dict
) -> None:
    """An attacker knowing the victim's id gains nothing without the key."""
    from tests.conftest import FOREIGN_KEY

    forged = make_token(owner_id, key=FOREIGN_KEY)
    resp = client.get("/dashboard", params=TODAY, headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


def test_no_token_reaches_nothing(client: TestClient, owners_data: dict) -> None:
    for path, params in (
        ("/daily-logs", {"from": DAY, "to": DAY}),
        ("/goals/active", None),
        ("/dashboard", TODAY),
        ("/workout-sessions", {"from": DAY, "to": DAY}),
        ("/exercises", None),
        ("/photos", {"year": 2026, "month": 9}),
        ("/admin/metrics", TODAY),
    ):
        assert client.get(path, params=params).status_code == 401, path
