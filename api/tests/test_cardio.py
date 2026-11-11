"""Cardio sessions: idempotency, ownership and bounds."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import make_token

DAY = "2026-09-07"


def body(**overrides) -> dict:
    base = {
        "client_uuid": str(uuid.uuid4()),
        "session_date": DAY,
        "activity": "run",
        "duration_min": 32,
        "distance_km": 5.2,
    }
    base.update(overrides)
    return base


def test_a_session_round_trips(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post("/cardio-sessions", json=body(), headers=auth_headers)

    assert resp.status_code == 201
    assert resp.json()["activity"] == "run"
    assert resp.json()["duration_min"] == 32


def test_replaying_the_same_write_does_not_duplicate_it(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """What the offline queue does when a response is lost (§8)."""
    payload = body()

    first = client.post("/cardio-sessions", json=payload, headers=auth_headers)
    second = client.post("/cardio-sessions", json=payload, headers=auth_headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    listed = client.get(
        "/cardio-sessions", params={"from": DAY, "to": DAY}, headers=auth_headers
    ).json()
    assert len(listed) == 1


def test_distance_is_optional_and_absent_is_not_zero(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A class measures no distance. Recording 0 would be a claim we cannot make."""
    resp = client.post(
        "/cardio-sessions", json=body(activity="class", distance_km=None), headers=auth_headers
    )

    assert resp.status_code == 201
    assert resp.json()["distance_km"] is None


def test_impossible_values_are_refused(client: TestClient, auth_headers: dict[str, str]) -> None:
    for bad in ({"duration_min": 0}, {"duration_min": 1441}, {"distance_km": -1}):
        assert (
            client.post("/cardio-sessions", json=body(**bad), headers=auth_headers).status_code
            == 422
        )

    assert (
        client.post("/cardio-sessions", json=body(activity="teleport"), headers=auth_headers)
    ).status_code == 422


def test_you_cannot_see_another_users_cardio(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post("/cardio-sessions", json=body(), headers=auth_headers)

    other = {"Authorization": f"Bearer {make_token()}"}
    listed = client.get("/cardio-sessions", params={"from": DAY, "to": DAY}, headers=other).json()

    assert listed == []


def test_another_users_idempotency_key_is_not_confirmed(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """404, not 403: a 403 would confirm the key is in use."""
    payload = body()
    client.post("/cardio-sessions", json=payload, headers=auth_headers)

    other = {"Authorization": f"Bearer {make_token()}"}
    resp = client.post("/cardio-sessions", json=payload, headers=other)

    assert resp.status_code == 404


def test_a_user_id_in_the_body_is_refused(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/cardio-sessions",
        json=body(user_id=str(uuid.uuid4())),
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_an_unbounded_range_is_refused(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get(
        "/cardio-sessions", params={"from": "2020-01-01", "to": "2026-09-07"}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_the_endpoints_need_a_token(client: TestClient) -> None:
    assert client.post("/cardio-sessions", json=body()).status_code == 401
    assert client.get("/cardio-sessions", params={"from": DAY, "to": DAY}).status_code == 401
