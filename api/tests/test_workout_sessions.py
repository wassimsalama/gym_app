"""`/workout-sessions` (spec §6).

The idempotency cases matter most: the offline queue (§8) retries writes whose
responses were lost, and a duplicated session corrupts both volume and PRs.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.services.prs import epley_e1rm
from tests.conftest import make_token
from tests.test_exercises import make_exercise


def session_body(exercise_id: int, sets: list[tuple[float, int]], **overrides) -> dict:
    body = {
        "client_uuid": str(uuid.uuid4()),
        "session_date": "2026-09-07",
        "split": "push",
        "sets": [
            {"exercise_id": exercise_id, "set_number": i + 1, "weight_kg": w, "reps": r}
            for i, (w, r) in enumerate(sets)
        ],
    }
    body.update(overrides)
    return body


def test_requires_authentication(client: TestClient) -> None:
    assert client.post("/workout-sessions", json={}).status_code == 401
    assert (
        client.get(
            "/workout-sessions", params={"from": "2026-09-01", "to": "2026-09-07"}
        ).status_code
        == 401
    )


def test_saves_a_session_with_its_sets(client: TestClient, auth_headers: dict[str, str]) -> None:
    bench = make_exercise(client, auth_headers, "Barbell Bench Press")

    resp = client.post(
        "/workout-sessions",
        json=session_body(bench, [(100, 5), (100, 5), (100, 4)]),
        headers=auth_headers,
    )
    assert resp.status_code == 201

    session = resp.json()["session"]
    assert session["split"] == "push"
    assert [s["reps"] for s in session["sets"]] == [5, 5, 4]


def test_a_repeat_post_returns_the_same_session(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The core §8 guarantee: a retried write must not duplicate."""
    bench = make_exercise(client, auth_headers, "Barbell Bench Press")
    body = session_body(bench, [(100, 5)])

    first = client.post("/workout-sessions", json=body, headers=auth_headers)
    second = client.post("/workout-sessions", json=body, headers=auth_headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["session"]["id"] == second.json()["session"]["id"]

    listed = client.get(
        "/workout-sessions", params={"from": "2026-09-01", "to": "2026-09-30"}, headers=auth_headers
    ).json()
    assert len(listed) == 1


def test_a_repeat_post_does_not_re_announce_prs(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A flaky connection must not celebrate the same lift twice."""
    bench = make_exercise(client, auth_headers, "Barbell Bench Press")
    client.post("/workout-sessions", json=session_body(bench, [(100, 5)]), headers=auth_headers)

    body = session_body(bench, [(110, 5)])
    first = client.post("/workout-sessions", json=body, headers=auth_headers).json()
    second = client.post("/workout-sessions", json=body, headers=auth_headers).json()

    assert len(first["prs"]) == 1
    assert second["prs"] == []


def test_another_users_idempotency_key_is_refused(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    bench = make_exercise(client, auth_headers, "Barbell Bench Press")
    body = session_body(bench, [(100, 5)])
    client.post("/workout-sessions", json=body, headers=auth_headers)

    other = {"Authorization": f"Bearer {make_token()}"}
    assert client.post("/workout-sessions", json=body, headers=other).status_code == 403


def test_a_first_ever_session_sets_no_prs(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Spec §7.3 — nothing was beaten."""
    bench = make_exercise(client, auth_headers, "Barbell Bench Press")
    resp = client.post(
        "/workout-sessions", json=session_body(bench, [(100, 5)]), headers=auth_headers
    )
    assert resp.json()["prs"] == []


def test_beating_a_previous_session_reports_a_pr(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    bench = make_exercise(client, auth_headers, "Barbell Bench Press")
    client.post("/workout-sessions", json=session_body(bench, [(100, 5)]), headers=auth_headers)

    resp = client.post(
        "/workout-sessions", json=session_body(bench, [(105, 5)]), headers=auth_headers
    )
    [pr] = resp.json()["prs"]

    assert pr["exercise_name"] == "Barbell Bench Press"
    assert pr["e1rm"] == pytest.approx(epley_e1rm(105, 5), abs=0.01)
    assert pr["previous_e1rm"] == pytest.approx(epley_e1rm(100, 5), abs=0.01)


def test_the_stored_history_and_the_python_formula_agree(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The historical best is computed in SQL and the session's in Python.

    If those two formulas ever drift — the rep cap especially — PRs would fire
    at the wrong moments. A set that exactly ties must produce no PR, which is
    only true if both sides compute the identical number.
    """
    bench = make_exercise(client, auth_headers, "Barbell Bench Press")
    client.post("/workout-sessions", json=session_body(bench, [(100, 20)]), headers=auth_headers)

    # 20 reps and 12 reps score identically under the cap, so this ties exactly.
    resp = client.post(
        "/workout-sessions", json=session_body(bench, [(100, 12)]), headers=auth_headers
    )
    assert resp.json()["prs"] == []

    # A hair heavier must clear it.
    resp = client.post(
        "/workout-sessions", json=session_body(bench, [(100.5, 12)]), headers=auth_headers
    )
    assert len(resp.json()["prs"]) == 1


def test_another_users_history_does_not_count(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    """A strong stranger on the same catalogue lift must not suppress your PRs."""
    client.post(
        "/workout-sessions", json=session_body(shared_exercise, [(200, 5)]), headers=auth_headers
    )

    other = {"Authorization": f"Bearer {make_token()}"}
    client.post("/workout-sessions", json=session_body(shared_exercise, [(60, 5)]), headers=other)
    resp = client.post(
        "/workout-sessions", json=session_body(shared_exercise, [(65, 5)]), headers=other
    )
    assert len(resp.json()["prs"]) == 1


def test_a_seeded_exercise_is_visible_to_everyone(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    """Catalogue entries are shared; only user-created ones are private."""
    other = {"Authorization": f"Bearer {make_token()}"}
    for headers in (auth_headers, other):
        found = client.get("/exercises", params={"q": "bench"}, headers=headers).json()
        assert any(e["id"] == shared_exercise for e in found)


def test_a_session_may_have_no_sets(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Quick-log writes trained + split with no detail (spec §2.3)."""
    resp = client.post(
        "/workout-sessions",
        json={
            "client_uuid": str(uuid.uuid4()),
            "session_date": "2026-09-07",
            "split": "legs",
            "sets": [],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["session"]["sets"] == []


def test_an_unknown_exercise_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/workout-sessions", json=session_body(999999, [(100, 5)]), headers=auth_headers
    )
    assert resp.status_code == 422
    assert "Unknown exercise" in resp.json()["detail"]


def test_another_users_custom_exercise_is_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    mine = make_exercise(client, auth_headers, "Zercher Squat", "quads")

    other = {"Authorization": f"Bearer {make_token()}"}
    resp = client.post("/workout-sessions", json=session_body(mine, [(100, 5)]), headers=other)
    assert resp.status_code == 422


def test_invalid_sets_are_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    bench = make_exercise(client, auth_headers, "Barbell Bench Press")
    assert (
        client.post(
            "/workout-sessions", json=session_body(bench, [(100, 0)]), headers=auth_headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/workout-sessions", json=session_body(bench, [(100, 101)]), headers=auth_headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/workout-sessions", json=session_body(bench, [(-5, 5)]), headers=auth_headers
        ).status_code
        == 422
    )


def test_an_unknown_split_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    bench = make_exercise(client, auth_headers, "Barbell Bench Press")
    body = session_body(bench, [(100, 5)], split="cardio")
    assert client.post("/workout-sessions", json=body, headers=auth_headers).status_code == 422


def test_listing_is_newest_first_and_scoped(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    bench = make_exercise(client, auth_headers, "Barbell Bench Press")
    for day in ("2026-09-01", "2026-09-05", "2026-09-03"):
        client.post(
            "/workout-sessions",
            json=session_body(bench, [(100, 5)], session_date=day),
            headers=auth_headers,
        )

    listed = client.get(
        "/workout-sessions", params={"from": "2026-09-01", "to": "2026-09-30"}, headers=auth_headers
    ).json()
    assert [s["session_date"] for s in listed] == ["2026-09-05", "2026-09-03", "2026-09-01"]

    other = {"Authorization": f"Bearer {make_token()}"}
    assert (
        client.get(
            "/workout-sessions", params={"from": "2026-09-01", "to": "2026-09-30"}, headers=other
        ).json()
        == []
    )


def test_bad_ranges_are_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert (
        client.get(
            "/workout-sessions",
            params={"from": "2026-09-05", "to": "2026-09-01"},
            headers=auth_headers,
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/workout-sessions",
            params={"from": "2000-01-01", "to": "2026-09-01"},
            headers=auth_headers,
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    ("weight", "reps"),
    [
        (102.5, 5),  # e1rm 119.5833... — the case that shipped broken
        (100.0, 12),  # e1rm 140.0 exactly — terminating, passed even when broken
        (77.5, 7),  # e1rm 95.583...
        (60.0, 3),  # e1rm 66.0 exactly
        (142.5, 11),  # e1rm 194.75
    ],
)
def test_repeating_a_best_lift_is_never_a_pr(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int, weight: float, reps: int
) -> None:
    """Regression: the historical best is aggregated in SQL, the session's is
    computed in Python.

    Those paths must agree exactly. They once did not — SQLAlchemy quantised the
    aggregate to weight_kg's numeric(6,2) scale, so 119.5833... came back as
    119.58 and repeating a best set announced a PR it had not earned. Weights
    whose e1RM terminates in two decimals hid the bug entirely, which is why the
    original test missed it.
    """
    body = session_body(shared_exercise, [(weight, reps)])
    assert client.post("/workout-sessions", json=body, headers=auth_headers).status_code == 201

    repeat = client.post(
        "/workout-sessions",
        json=session_body(shared_exercise, [(weight, reps)], session_date="2026-09-14"),
        headers=auth_headers,
    )
    assert repeat.json()["prs"] == [], f"{weight}x{reps} falsely reported a PR"


def test_the_smallest_real_increment_still_counts(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    """The tolerance must not be so wide it swallows an actual plate change."""
    client.post(
        "/workout-sessions", json=session_body(shared_exercise, [(102.5, 5)]), headers=auth_headers
    )

    # 1.25 kg is the smallest plate the app offers (§2.3).
    resp = client.post(
        "/workout-sessions",
        json=session_body(shared_exercise, [(103.75, 5)], session_date="2026-09-14"),
        headers=auth_headers,
    )
    assert len(resp.json()["prs"]) == 1


def test_one_more_rep_at_the_same_weight_is_a_pr(
    client: TestClient, auth_headers: dict[str, str], shared_exercise: int
) -> None:
    client.post(
        "/workout-sessions", json=session_body(shared_exercise, [(102.5, 5)]), headers=auth_headers
    )
    resp = client.post(
        "/workout-sessions",
        json=session_body(shared_exercise, [(102.5, 6)], session_date="2026-09-14"),
        headers=auth_headers,
    )
    assert len(resp.json()["prs"]) == 1
