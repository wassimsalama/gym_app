"""`GET /dashboard` (spec §6) — one request, everything the home tab renders."""

from fastapi.testclient import TestClient

from tests.conftest import make_token


def seed(client: TestClient, headers: dict[str, str], weights: list[tuple[str, float]]) -> None:
    for day, kg in weights:
        client.put(f"/daily-logs/{day}", json={"weight_kg": kg}, headers=headers)


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/dashboard").status_code == 401


def test_shape_is_complete_even_with_no_data(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A day-one user must get every key, so the app renders without guards."""
    body = client.get("/dashboard", headers=auth_headers).json()

    assert set(body) == {
        "streaks",
        "weight",
        "goal",
        "tdee",
        "volume",
        "prs_recent",
        "suggestions",
        "recap",
    }
    assert body["weight"] == {
        "current_smoothed_kg": None,
        "delta_since_start_kg": None,
        "series": [],
    }
    assert body["goal"] is None
    assert body["tdee"] == {"estimate_kcal": None, "days_of_data": 0, "reliable": False}
    assert body["volume"] == []
    assert body["suggestions"] == []
    assert body["recap"] is None


def test_series_carries_raw_and_smoothed(client: TestClient, auth_headers: dict[str, str]) -> None:
    seed(
        client,
        auth_headers,
        [("2026-09-01", 90.0), ("2026-09-02", 89.0), ("2026-09-03", 91.0)],
    )
    body = client.get("/dashboard", headers=auth_headers).json()
    series = body["weight"]["series"]

    assert [p["date"] for p in series] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert [p["raw_kg"] for p in series] == [90.0, 89.0, 91.0]
    # Third point averages all three; the spike is damped.
    assert series[-1]["smoothed_kg"] == 90.0
    assert body["weight"]["current_smoothed_kg"] == 90.0


def test_days_without_a_weight_are_absent_from_the_series(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    seed(client, auth_headers, [("2026-09-01", 90.0)])
    client.put("/daily-logs/2026-09-02", json={"calories": 2400}, headers=auth_headers)

    series = client.get("/dashboard", headers=auth_headers).json()["weight"]["series"]
    assert [p["date"] for p in series] == ["2026-09-01"]


def test_goal_block_reports_progress(client: TestClient, auth_headers: dict[str, str]) -> None:
    seed(client, auth_headers, [("2026-09-01", 90.0)])
    client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)
    seed(client, auth_headers, [("2026-09-02", 89.0), ("2026-09-03", 88.0)])

    body = client.get("/dashboard", headers=auth_headers).json()
    assert body["goal"]["progress_pct"] > 0
    assert body["weight"]["delta_since_start_kg"] < 0  # lost weight since start


def test_delta_is_measured_against_the_goal_start_not_the_first_ever_log(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    seed(client, auth_headers, [("2026-06-01", 100.0)])
    seed(client, auth_headers, [("2026-09-01", 90.0)])
    client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)
    seed(client, auth_headers, [("2026-09-02", 89.0), ("2026-09-03", 88.0)])

    body = client.get("/dashboard", headers=auth_headers).json()
    # Start weight is 90 (latest log when the goal opened), so the delta is
    # about -1.x, not -11 measured from June.
    assert -3.0 < body["weight"]["delta_since_start_kg"] < 0


def test_a_flat_trend_refuses_to_project(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Spec §2.6: status from the trend, not wishful maths."""
    seed(client, auth_headers, [(f"2026-09-{d:02d}", 90.0) for d in range(1, 15)])
    client.post(
        "/goals",
        json={"goal_weight_kg": 80, "target_date": "2026-12-01"},
        headers=auth_headers,
    )

    goal = client.get("/dashboard", headers=auth_headers).json()["goal"]
    assert goal["projected_date"] is None
    assert goal["on_track"] is None


def test_a_steady_cut_projects_a_date(client: TestClient, auth_headers: dict[str, str]) -> None:
    seed(client, auth_headers, [(f"2026-09-{d:02d}", 90.0 - 0.1 * d) for d in range(1, 22)])
    client.post("/goals", json={"goal_weight_kg": 85}, headers=auth_headers)

    goal = client.get("/dashboard", headers=auth_headers).json()["goal"]
    assert goal["projected_date"] is not None


def test_dashboard_is_scoped_to_its_owner(client: TestClient, auth_headers: dict[str, str]) -> None:
    seed(client, auth_headers, [("2026-09-01", 90.0)])

    other = {"Authorization": f"Bearer {make_token()}"}
    body = client.get("/dashboard", headers=other).json()
    assert body["weight"]["series"] == []
    assert body["goal"] is None
