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


# --- PATCH /goals/active ---------------------------------------------------


def test_patch_requires_authentication(client: TestClient) -> None:
    assert client.patch("/goals/active", json={"goal_weight_kg": 78}).status_code == 401


def test_patch_404s_without_an_active_goal(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.patch("/goals/active", json={"goal_weight_kg": 78}, headers=auth_headers)
    assert resp.status_code == 404


def test_patch_changes_the_target_without_moving_the_baseline(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The whole reason PATCH exists: editing a target must not reset progress."""
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    created = client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers).json()

    updated = client.patch(
        "/goals/active", json={"goal_weight_kg": 78}, headers=auth_headers
    ).json()

    assert updated["id"] == created["id"]  # same goal, not a new one
    assert Decimal(updated["goal_weight_kg"]) == Decimal("78.00")
    assert Decimal(updated["start_weight_kg"]) == Decimal("90.00")
    assert updated["start_date"] == "2026-09-01"


def test_patch_leaves_the_baseline_alone_even_after_newer_weights(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)
    log_weight(client, auth_headers, "2026-09-20", 86.0)

    updated = client.patch(
        "/goals/active", json={"goal_weight_kg": 79}, headers=auth_headers
    ).json()
    assert Decimal(updated["start_weight_kg"]) == Decimal("90.00")


def test_patch_can_set_and_clear_a_target_date(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)

    with_date = client.patch(
        "/goals/active", json={"target_date": "2026-12-01"}, headers=auth_headers
    ).json()
    assert with_date["target_date"] == "2026-12-01"

    cleared = client.patch("/goals/active", json={"target_date": None}, headers=auth_headers).json()
    assert cleared["target_date"] is None


def test_patch_leaves_unmentioned_fields_untouched(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    client.post(
        "/goals", json={"goal_weight_kg": 80, "target_date": "2026-12-01"}, headers=auth_headers
    )

    updated = client.patch(
        "/goals/active", json={"goal_weight_kg": 78}, headers=auth_headers
    ).json()
    assert updated["target_date"] == "2026-12-01"


def test_patch_rejects_an_empty_body_and_bad_values(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)

    assert client.patch("/goals/active", json={}, headers=auth_headers).status_code == 422
    assert (
        client.patch("/goals/active", json={"goal_weight_kg": 0}, headers=auth_headers).status_code
        == 422
    )
    # start_weight_kg used to be refused here. It is editable as of DECISION
    # 1(a); the guard that matters is that unknown fields are still refused, so
    # nothing else can be smuggled onto the goal.
    assert (
        client.patch(
            "/goals/active", json={"start_date": "2026-01-01"}, headers=auth_headers
        ).status_code
        == 422
    )
    assert (
        client.patch("/goals/active", json={"user_id": 1}, headers=auth_headers).status_code == 422
    )


def test_patch_cannot_reach_another_users_goal(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_weight(client, auth_headers, "2026-09-01", 90.0)
    client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)

    other = {"Authorization": f"Bearer {make_token()}"}
    assert (
        client.patch("/goals/active", json={"goal_weight_kg": 60}, headers=other).status_code == 404
    )


# --- editing the baseline (DECISION 1(a), a deliberate §7.1 deviation) -------


def test_the_starting_weight_can_be_corrected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A typo in the baseline must be fixable without losing the goal."""
    client.put("/daily-logs/2026-09-01", json={"weight_kg": 100}, headers=auth_headers)
    client.post("/goals", json={"goal_weight_kg": 90}, headers=auth_headers)

    resp = client.patch("/goals/active", json={"start_weight_kg": 105}, headers=auth_headers)

    assert resp.status_code == 200
    assert Decimal(resp.json()["start_weight_kg"]) == Decimal("105")
    assert Decimal(resp.json()["goal_weight_kg"]) == Decimal("90")


def test_correcting_the_baseline_does_not_start_a_new_goal(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.put("/daily-logs/2026-09-01", json={"weight_kg": 100}, headers=auth_headers)
    created = client.post("/goals", json={"goal_weight_kg": 90}, headers=auth_headers).json()

    client.patch("/goals/active", json={"start_weight_kg": 105}, headers=auth_headers)
    after = client.get("/goals/active", headers=auth_headers).json()

    assert after["id"] == created["id"]
    assert after["start_date"] == created["start_date"]


def test_an_impossible_starting_weight_is_refused(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.put("/daily-logs/2026-09-01", json={"weight_kg": 100}, headers=auth_headers)
    client.post("/goals", json={"goal_weight_kg": 90}, headers=auth_headers)

    for bad in (0, -5, 10_000):
        resp = client.patch("/goals/active", json={"start_weight_kg": bad}, headers=auth_headers)
        assert resp.status_code == 422, bad
