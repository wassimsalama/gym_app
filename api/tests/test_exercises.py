"""`/exercises` — search, custom creation, and the last-sets prefill (spec §6)."""

from fastapi.testclient import TestClient

from tests.conftest import make_token


def make_exercise(
    client: TestClient, headers: dict[str, str], name: str, group: str = "chest"
) -> int:
    resp = client.post("/exercises", json={"name": name, "muscle_group": group}, headers=headers)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/exercises").status_code == 401
    assert client.post("/exercises", json={"name": "x", "muscle_group": "chest"}).status_code == 401


def test_creates_a_custom_exercise(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/exercises",
        json={"name": "Zercher Squat", "muscle_group": "quads", "equipment": "barbell"},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    body = resp.json()
    assert body["name"] == "Zercher Squat"
    assert body["muscle_group"] == "quads"
    assert body["source"] == "custom"


def test_creating_the_same_name_twice_returns_the_first(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The queue retries writes (§8); a duplicate would split that lift's history."""
    first = client.post(
        "/exercises", json={"name": "Zercher Squat", "muscle_group": "quads"}, headers=auth_headers
    ).json()
    again = client.post(
        "/exercises", json={"name": "zercher squat", "muscle_group": "quads"}, headers=auth_headers
    ).json()
    assert first["id"] == again["id"]


def test_rejects_a_muscle_group_outside_the_vocabulary(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Volume rings bucket by exactly these names (§7.6); free text would break them."""
    resp = client.post(
        "/exercises", json={"name": "Jogging", "muscle_group": "cardio"}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_rejects_an_empty_name(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/exercises", json={"name": "", "muscle_group": "chest"}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_search_finds_a_partial_word(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Typing "benc" must match before the word is finished."""
    make_exercise(client, auth_headers, "Barbell Bench Press")

    found = client.get("/exercises", params={"q": "benc"}, headers=auth_headers).json()
    assert any(e["name"] == "Barbell Bench Press" for e in found)


def test_search_matches_a_later_word(client: TestClient, auth_headers: dict[str, str]) -> None:
    make_exercise(client, auth_headers, "Barbell Bench Press")

    found = client.get("/exercises", params={"q": "bench"}, headers=auth_headers).json()
    assert any(e["name"] == "Barbell Bench Press" for e in found)


def test_search_without_a_term_lists_exercises(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    make_exercise(client, auth_headers, "Barbell Bench Press")
    assert len(client.get("/exercises", headers=auth_headers).json()) >= 1


def test_search_is_capped(client: TestClient, auth_headers: dict[str, str]) -> None:
    for i in range(25):
        make_exercise(client, auth_headers, f"Curl Variation {i}")
    found = client.get("/exercises", params={"q": "curl"}, headers=auth_headers).json()
    assert len(found) == 20


def test_a_users_own_exercises_come_first(client: TestClient, auth_headers: dict[str, str]) -> None:
    """A custom entry exists because the catalogue was missing something."""
    make_exercise(client, auth_headers, "Aardvark Press")
    found = client.get("/exercises", params={"q": "press"}, headers=auth_headers).json()
    assert found[0]["source"] == "custom"


def test_customs_are_private_to_their_creator(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    make_exercise(client, auth_headers, "Zercher Squat")

    other = {"Authorization": f"Bearer {make_token()}"}
    found = client.get("/exercises", params={"q": "zercher"}, headers=other).json()
    assert found == []


def test_last_sets_is_empty_for_an_exercise_never_performed(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The app wants a blank first set, not a 404."""
    exercise_id = make_exercise(client, auth_headers, "Barbell Bench Press")

    body = client.get(f"/exercises/{exercise_id}/last-sets", headers=auth_headers).json()
    assert body == {"exercise_id": exercise_id, "session_date": None, "sets": []}


def test_last_sets_404s_for_an_unknown_exercise(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.get("/exercises/999999/last-sets", headers=auth_headers).status_code == 404


def test_last_sets_404s_for_another_users_custom(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    exercise_id = make_exercise(client, auth_headers, "Zercher Squat")

    other = {"Authorization": f"Bearer {make_token()}"}
    assert client.get(f"/exercises/{exercise_id}/last-sets", headers=other).status_code == 404
