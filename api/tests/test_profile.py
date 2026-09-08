"""The display-unit toggle (PATCH /me)."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import make_token


def test_the_default_unit_is_pounds(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/health-auth", headers=auth_headers).json()["unit"] == "lb"


def test_switching_to_kilos_persists(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.patch("/me", json={"unit": "kg"}, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["unit"] == "kg"
    # Read it back through the endpoint the app actually uses.
    assert client.get("/health-auth", headers=auth_headers).json()["unit"] == "kg"


def test_an_unknown_unit_is_refused(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.patch("/me", json={"unit": "stone"}, headers=auth_headers).status_code == 422
    assert client.get("/health-auth", headers=auth_headers).json()["unit"] == "lb"


def test_a_user_id_in_the_body_is_refused(client: TestClient, auth_headers: dict[str, str]) -> None:
    """extra="forbid" — the acting user comes from the token, never the body."""
    resp = client.patch(
        "/me",
        json={"unit": "kg", "user_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_changing_your_unit_does_not_touch_anyone_else(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    other = {"Authorization": f"Bearer {make_token()}"}
    client.get("/health-auth", headers=other)  # materialise their profile

    client.patch("/me", json={"unit": "kg"}, headers=auth_headers)

    assert client.get("/health-auth", headers=other).json()["unit"] == "lb"


def test_the_endpoint_needs_a_token(client: TestClient) -> None:
    assert client.patch("/me", json={"unit": "kg"}).status_code == 401
