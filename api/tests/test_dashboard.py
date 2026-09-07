"""`GET /dashboard` (spec §6) — one request, everything the home tab renders.

`date` is supplied by the client: §6 forbids the server deriving "today" from
UTC, and streaks, Monday-anchored volume and the recap all need a calendar day.
"""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import make_token
from tests.test_exercises import make_exercise

# 2026-09-30 is a Wednesday; the Monday of its week is 2026-09-28.
TODAY = "2026-09-30"
MONDAY = "2026-09-28"


def dashboard(client: TestClient, headers: dict[str, str], on: str = TODAY) -> dict:
    resp = client.get("/dashboard", params={"date": on}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def seed(client: TestClient, headers: dict[str, str], weights: list[tuple[str, float]]) -> None:
    for day, kg in weights:
        client.put(f"/daily-logs/{day}", json={"weight_kg": kg}, headers=headers)


def log_session(
    client: TestClient,
    headers: dict[str, str],
    day: str,
    exercise_id: int,
    sets: list[tuple[float, int]],
) -> dict:
    return client.post(
        "/workout-sessions",
        json={
            "client_uuid": str(uuid.uuid4()),
            "session_date": day,
            "split": "push",
            "sets": [
                {"exercise_id": exercise_id, "set_number": i + 1, "weight_kg": w, "reps": r}
                for i, (w, r) in enumerate(sets)
            ],
        },
        headers=headers,
    ).json()


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/dashboard", params={"date": TODAY}).status_code == 401


def test_date_is_required(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Without it the server would have to invent a today, which §6 forbids."""
    assert client.get("/dashboard", headers=auth_headers).status_code == 422


def test_shape_is_complete_with_no_data(client: TestClient, auth_headers: dict[str, str]) -> None:
    body = dashboard(client, auth_headers)

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
    assert body["streaks"] == {"logged_14": 0, "trained_14": 0}
    assert body["weight"]["series"] == []
    assert body["goal"] is None
    assert body["tdee"] == {"estimate_kcal": None, "days_of_data": 0, "reliable": False}
    assert body["prs_recent"] == []
    # Every targeted group is present even before anything is logged.
    assert {r["muscle_group"] for r in body["volume"]} >= {"chest", "back", "quads"}
    assert all(r["sets_this_week"] == 0 for r in body["volume"])


# --- weight and goal -------------------------------------------------------


def test_series_carries_raw_and_smoothed(client: TestClient, auth_headers: dict[str, str]) -> None:
    seed(client, auth_headers, [("2026-09-28", 90.0), ("2026-09-29", 89.0), ("2026-09-30", 91.0)])
    series = dashboard(client, auth_headers)["weight"]["series"]

    assert [p["raw_kg"] for p in series] == [90.0, 89.0, 91.0]
    assert series[-1]["smoothed_kg"] == 90.0


def test_goal_block_carries_the_numbers_behind_the_percentage(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    seed(client, auth_headers, [("2026-09-01", 90.0)])
    client.post("/goals", json={"goal_weight_kg": 80}, headers=auth_headers)

    goal = dashboard(client, auth_headers)["goal"]
    assert goal["start_weight_kg"] == 90.0
    assert goal["goal_weight_kg"] == 80.0


def test_progress_is_zero_when_moving_away_from_the_goal(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    seed(client, auth_headers, [("2026-09-01", 90.0)])
    client.post("/goals", json={"goal_weight_kg": 77}, headers=auth_headers)
    seed(client, auth_headers, [("2026-09-07", 104.0)])

    goal = dashboard(client, auth_headers)["goal"]
    assert goal["progress_pct"] == 0.0
    assert goal["start_weight_kg"] == 90.0


def test_series_is_bounded_at_a_year(client: TestClient, auth_headers: dict[str, str]) -> None:
    seed(client, auth_headers, [("2020-01-01", 110.0), (TODAY, 86.0)])
    series = dashboard(client, auth_headers)["weight"]["series"]
    assert [p["date"] for p in series] == [TODAY]


# --- streaks ---------------------------------------------------------------


def test_streaks_count_the_rolling_window(client: TestClient, auth_headers: dict[str, str]) -> None:
    seed(client, auth_headers, [(f"2026-09-{d:02d}", 90.0) for d in range(24, 31)])
    body = dashboard(client, auth_headers)
    assert body["streaks"]["logged_14"] == 7


def test_entries_older_than_the_window_do_not_count(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    seed(client, auth_headers, [("2026-09-01", 90.0), ("2026-09-02", 90.0), (TODAY, 90.0)])
    body = dashboard(client, auth_headers)
    assert body["streaks"]["logged_14"] == 1


def test_a_workout_session_counts_as_trained(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    """Spec §7.6: a session counts whether or not the flag was also set."""
    log_session(client, auth_headers, TODAY, shared_exercise, [(100, 5)])
    body = dashboard(client, auth_headers)
    assert body["streaks"]["trained_14"] == 1


def test_the_trained_flag_alone_also_counts(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.put(
        f"/daily-logs/{TODAY}", json={"trained": True, "split": "legs"}, headers=auth_headers
    )
    body = dashboard(client, auth_headers)
    assert body["streaks"]["trained_14"] == 1


def test_a_flag_and_a_session_on_one_day_count_once(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    log_session(client, auth_headers, TODAY, shared_exercise, [(100, 5)])
    client.put(f"/daily-logs/{TODAY}", json={"trained": True}, headers=auth_headers)

    body = dashboard(client, auth_headers)
    assert body["streaks"]["trained_14"] == 1


# --- volume rings ----------------------------------------------------------


def test_volume_counts_sets_in_the_current_week(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    log_session(client, auth_headers, MONDAY, shared_exercise, [(100, 5), (100, 5), (100, 5)])
    log_session(client, auth_headers, TODAY, shared_exercise, [(100, 5), (100, 5)])

    volume = {r["muscle_group"]: r for r in dashboard(client, auth_headers)["volume"]}
    assert volume["chest"]["sets_this_week"] == 5
    assert volume["chest"]["weekly_target"] == 10


def test_last_weeks_sets_do_not_count(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    """The week is Monday-anchored; Sunday belongs to the week before."""
    log_session(client, auth_headers, "2026-09-27", shared_exercise, [(100, 5), (100, 5)])

    volume = {r["muscle_group"]: r for r in dashboard(client, auth_headers)["volume"]}
    assert volume["chest"]["sets_this_week"] == 0


def test_monday_itself_belongs_to_the_current_week(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    log_session(client, auth_headers, MONDAY, shared_exercise, [(100, 5)])
    volume = {r["muscle_group"]: r for r in dashboard(client, auth_headers)["volume"]}
    assert volume["chest"]["sets_this_week"] == 1


# --- tdee ------------------------------------------------------------------


def test_tdee_collects_before_it_estimates(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    for i in range(5):
        day = f"2026-09-{26 + i:02d}" if 26 + i <= 30 else None
        if day:
            client.put(
                f"/daily-logs/{day}",
                json={"weight_kg": 90.0, "calories": 2500},
                headers=auth_headers,
            )

    body = dashboard(client, auth_headers)
    assert body["tdee"]["estimate_kcal"] is None
    assert body["tdee"]["reliable"] is False
    assert body["tdee"]["days_of_data"] == 5


def test_tdee_estimates_once_there_is_enough(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Flat weight on 2500 kcal means 2500 is maintenance."""
    from datetime import date, timedelta

    end = date(2026, 9, 30)
    for i in range(35):
        day = end - timedelta(days=34 - i)
        client.put(
            f"/daily-logs/{day}", json={"weight_kg": 90.0, "calories": 2500}, headers=auth_headers
        )

    body = dashboard(client, auth_headers)
    assert body["tdee"]["reliable"] is True
    assert body["tdee"]["estimate_kcal"] == 2500


# --- recent PRs ------------------------------------------------------------


def test_recent_prs_appear(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    log_session(client, auth_headers, "2026-09-01", shared_exercise, [(100, 5)])
    log_session(client, auth_headers, TODAY, shared_exercise, [(110, 5)])

    [pr] = dashboard(client, auth_headers)["prs_recent"]
    assert pr["exercise_name"] == "Barbell Bench Press"
    assert pr["e1rm"] > pr["previous_e1rm"]
    assert pr["achieved_on"] == TODAY


def test_a_first_ever_lift_is_not_a_recent_pr(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    log_session(client, auth_headers, TODAY, shared_exercise, [(100, 5)])
    assert dashboard(client, auth_headers)["prs_recent"] == []


def test_an_older_pr_falls_out_of_the_window(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    log_session(client, auth_headers, "2026-08-01", shared_exercise, [(100, 5)])
    log_session(client, auth_headers, "2026-09-01", shared_exercise, [(110, 5)])

    assert dashboard(client, auth_headers)["prs_recent"] == []


# --- isolation -------------------------------------------------------------


def test_dashboard_is_scoped_to_its_owner(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    seed(client, auth_headers, [(TODAY, 90.0)])
    log_session(client, auth_headers, TODAY, shared_exercise, [(100, 5)])

    other = {"Authorization": f"Bearer {make_token()}"}
    body = dashboard(client, other)

    assert body["weight"]["series"] == []
    assert body["goal"] is None
    assert body["streaks"] == {"logged_14": 0, "trained_14": 0}
    assert all(r["sets_this_week"] == 0 for r in body["volume"])
    assert body["prs_recent"] == []


def test_a_custom_exercise_still_buckets_into_its_group(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    squat = make_exercise(client, auth_headers, "Zercher Squat", "quads")
    log_session(client, auth_headers, TODAY, squat, [(80, 5), (80, 5)])

    volume = {r["muscle_group"]: r for r in dashboard(client, auth_headers)["volume"]}
    assert volume["quads"]["sets_this_week"] == 2
