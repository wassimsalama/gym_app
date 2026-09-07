"""`POST /goals` and `GET /goals/active` (spec §6, §2.6)."""

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import make_token


def log_weight(client: TestClient, headers: dict[str, str], day: str, kg: float) -> None:
    assert (
        client.put(f"/daily-logs/{day}", json={"weight_kg": kg}, headers=headers).status_code == 200
    )


def test_requires_authentication(client: TestClient) -> None:
    assert client.post("/goals", json={"goal_weight_kg": 80}).status_code == 401
    assert client.get("/goals/active").status_code == 401


def test_active_goal_is_404_before_one_exists(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/goals/active", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No active goal"


def test_a_goal_needs_a_logged_weight_first(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Start weight is taken from the log, so there must be one (§2.6)."""
    resp = client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)
    assert resp.status_code == 422
    assert "Log a weight" in resp.json()["detail"]


def test_start_weight_and_date_come_from_the_latest_log(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    log_weight(client, auth_headers, "2026-09-05", 89.4)

    resp = client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)

    assert resp.status_code == 201
    body = resp.json()
    assert Decimal(body["start_weight_kg"]) == Decimal("89.40")
    assert body["start_date"] == "2026-09-05"
    assert Decimal(body["goal_weight_kg"]) == Decimal("80.00")
    assert body["status"] == "active"
    assert body["target_date"] is None


def test_days_without_a_weight_are_skipped_when_choosing_the_start(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A later macros-only row must not become the goal's baseline."""
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    client.put("/daily-logs/2026-09-09", json={"calories": 2400}, headers=auth_headers)

    body = client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers).json()
    assert body["start_date"] == "2026-09-01"
    assert Decimal(body["start_weight_kg"]) == Decimal("90.00")


def test_target_date_is_stored_when_supplied(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    body = client.post(
        "/goals",
        json={"goal_weight_kg": 80, "target_date": "2026-12-25"},
        headers=auth_headers,
    ).json()
    assert body["target_date"] == "2026-12-25"


def test_a_new_goal_closes_the_previous_one(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    first = client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers).json()
    second = client.post("/goals", json={"goal_weight_kg": 78}, headers=auth_headers).json()

    assert first["id"] != second["id"]
    active = client.get("/goals/active", headers=auth_headers).json()
    assert active["id"] == second["id"]
    assert Decimal(active["goal_weight_kg"]) == Decimal("78.00")


def test_a_goal_to_gain_weight_is_allowed(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Bulking is a goal too — nothing may assume goal < start."""
    log_weight(client, auth_headers, "2026-09-01", 70.0)
    body = client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers).json()
    assert Decimal(body["goal_weight_kg"]) > Decimal(body["start_weight_kg"])


def test_invalid_goal_weights_are_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    assert (
        client.post("/goals", json={"goal_weight_kg": 0}, headers=auth_headers).status_code == 422
    )
    assert (
        client.post("/goals", json={"goal_weight_kg": 5000}, headers=auth_headers).status_code
        == 422
    )
    assert client.post("/goals", json={}, headers=auth_headers).status_code == 422


def test_goals_are_scoped_to_their_owner(client: TestClient, auth_headers: dict[str, str]) -> None:
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)

    other = {"Authorization": f"Bearer {make_token()}"}
    assert client.get("/goals/active", headers=other).status_code == 404


def test_one_users_new_goal_does_not_close_anothers(client: TestClient) -> None:
    first = {"Authorization": f"Bearer {make_token()}"}
    second = {"Authorization": f"Bearer {make_token()}"}

    for headers in (first, second):
        log_weight(client, headers, "2026-09-01", 90.0)
        client.post("/goals", json={"goal_weight_kg": 80}, headers=headers)

    # The second user's goal must not have abandoned the first user's.
    assert client.get("/goals/active", headers=first).status_code == 200
