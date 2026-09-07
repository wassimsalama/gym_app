"""`PUT /daily-logs/{date}` and `GET /daily-logs` (spec §6).

The load-bearing behaviour is the merge: two tabs write to the same row on the
same day and must not erase each other.
"""

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import make_token

DATE = "2026-09-01"


def test_requires_authentication(client: TestClient) -> None:
    assert client.put(f"/daily-logs/{DATE}", json={"weight_kg": 80}).status_code == 401
    assert client.get("/daily-logs", params={"from": DATE, "to": DATE}).status_code == 401


def test_creates_a_row(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.put(f"/daily-logs/{DATE}", json={"weight_kg": 84.2}, headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["log_date"] == DATE
    assert Decimal(body["weight_kg"]) == Decimal("84.20")
    assert body["calories"] is None


def test_upserts_rather_than_duplicating(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.put(f"/daily-logs/{DATE}", json={"weight_kg": 84.2}, headers=auth_headers)
    resp = client.put(f"/daily-logs/{DATE}", json={"weight_kg": 83.9}, headers=auth_headers)

    assert Decimal(resp.json()["weight_kg"]) == Decimal("83.90")
    listed = client.get(
        "/daily-logs", params={"from": DATE, "to": DATE}, headers=auth_headers
    ).json()
    assert len(listed) == 1


def test_unprovided_fields_are_left_alone(client: TestClient, auth_headers: dict[str, str]) -> None:
    """The whole point of the merge: weight must not blank out macros."""
    client.put(
        f"/daily-logs/{DATE}",
        json={"calories": 2400, "protein_g": 180, "carbs_g": 250, "fat_g": 70},
        headers=auth_headers,
    )
    resp = client.put(f"/daily-logs/{DATE}", json={"weight_kg": 84.2}, headers=auth_headers)

    body = resp.json()
    assert body["calories"] == 2400
    assert body["protein_g"] == 180
    assert Decimal(body["weight_kg"]) == Decimal("84.20")


def test_an_explicit_null_does_clear_a_field(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Unset means "leave alone"; an explicit null means "erase". They differ."""
    client.put(f"/daily-logs/{DATE}", json={"calories": 2400}, headers=auth_headers)
    resp = client.put(f"/daily-logs/{DATE}", json={"calories": None}, headers=auth_headers)
    assert resp.json()["calories"] is None


def test_repeated_identical_writes_are_stable(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The offline queue (§8) retries; retries must not change the outcome."""
    payload = {"weight_kg": 84.2, "trained": True, "split": "push"}
    first = client.put(f"/daily-logs/{DATE}", json=payload, headers=auth_headers).json()
    second = client.put(f"/daily-logs/{DATE}", json=payload, headers=auth_headers).json()
    assert first == second


def test_a_day_may_hold_only_trained(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Spec §5: the measure columns are independently nullable."""
    resp = client.put(
        f"/daily-logs/{DATE}", json={"trained": True, "split": "legs"}, headers=auth_headers
    )
    body = resp.json()
    assert body["trained"] is True
    assert body["split"] == "legs"
    assert body["weight_kg"] is None
    assert body["calories"] is None


def test_empty_body_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.put(f"/daily-logs/{DATE}", json={}, headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["detail"] == "No fields to update"


def test_unknown_fields_are_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.put(f"/daily-logs/{DATE}", json={"weight_lb": 185}, headers=auth_headers)
    assert resp.status_code == 422


def test_out_of_range_values_return_422_not_500(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """numeric(5,2) would otherwise blow up in the driver."""
    assert (
        client.put(
            f"/daily-logs/{DATE}", json={"weight_kg": 1500}, headers=auth_headers
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/daily-logs/{DATE}", json={"calories": 99999}, headers=auth_headers
        ).status_code
        == 422
    )
    assert (
        client.put(f"/daily-logs/{DATE}", json={"weight_kg": -5}, headers=auth_headers).status_code
        == 422
    )


def test_unknown_split_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.put(f"/daily-logs/{DATE}", json={"split": "cardio"}, headers=auth_headers)
    assert resp.status_code == 422


def test_listing_is_ordered_oldest_first(client: TestClient, auth_headers: dict[str, str]) -> None:
    for day, weight in [("2026-09-03", 84.0), ("2026-09-01", 85.0), ("2026-09-02", 84.5)]:
        client.put(f"/daily-logs/{day}", json={"weight_kg": weight}, headers=auth_headers)

    listed = client.get(
        "/daily-logs", params={"from": "2026-09-01", "to": "2026-09-03"}, headers=auth_headers
    ).json()
    assert [row["log_date"] for row in listed] == ["2026-09-01", "2026-09-02", "2026-09-03"]


def test_listing_range_is_inclusive_at_both_ends(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    for day in ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03"]:
        client.put(f"/daily-logs/{day}", json={"weight_kg": 80}, headers=auth_headers)

    listed = client.get(
        "/daily-logs", params={"from": "2026-09-01", "to": "2026-09-02"}, headers=auth_headers
    ).json()
    assert [row["log_date"] for row in listed] == ["2026-09-01", "2026-09-02"]


def test_inverted_range_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get(
        "/daily-logs", params={"from": "2026-09-03", "to": "2026-09-01"}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_absurd_range_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get(
        "/daily-logs", params={"from": "2000-01-01", "to": "2026-09-01"}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_users_cannot_see_each_others_logs(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.put(f"/daily-logs/{DATE}", json={"weight_kg": 84.2}, headers=auth_headers)

    other = {"Authorization": f"Bearer {make_token()}"}
    listed = client.get("/daily-logs", params={"from": DATE, "to": DATE}, headers=other).json()
    assert listed == []
