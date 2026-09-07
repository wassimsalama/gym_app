"""First-party analytics — the arithmetic, and who is allowed to see it."""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import UserActivity
from app.services.metrics import Cohort, active_in_window, rate, retention, stickiness
from tests.conftest import make_token

MONDAY = date(2026, 9, 7)


def days(anchor: date, offsets: list[int]) -> dict:
    return {anchor - timedelta(days=o): {f"u{o}"} for o in offsets}


# --- the arithmetic --------------------------------------------------------


def test_nobody_active_is_zero() -> None:
    assert active_in_window({}, as_of=MONDAY, days=7) == 0


def test_the_window_includes_today() -> None:
    assert active_in_window({MONDAY: {"a"}}, as_of=MONDAY, days=1) == 1


def test_the_window_excludes_the_day_beyond_it() -> None:
    activity = {MONDAY - timedelta(days=7): {"a"}}
    assert active_in_window(activity, as_of=MONDAY, days=7) == 0
    assert active_in_window(activity, as_of=MONDAY, days=8) == 1


def test_a_user_active_on_several_days_counts_once() -> None:
    activity = {MONDAY: {"a"}, MONDAY - timedelta(days=1): {"a"}}
    assert active_in_window(activity, as_of=MONDAY, days=7) == 1


def test_distinct_users_are_counted_separately() -> None:
    activity = {MONDAY: {"a", "b"}, MONDAY - timedelta(days=1): {"c"}}
    assert active_in_window(activity, as_of=MONDAY, days=7) == 3


def test_rate_guards_the_empty_case() -> None:
    assert rate(0, 0) == 0.0
    assert rate(3, 4) == 75.0


def test_stickiness_is_daily_over_monthly() -> None:
    assert stickiness(5, 20) == 25.0
    assert stickiness(0, 0) == 0.0


# --- retention -------------------------------------------------------------


def test_a_week_with_no_signups_is_not_a_division_by_zero() -> None:
    cohort = retention({}, {}, week_start=MONDAY)
    assert cohort.signed_up == 0
    assert cohort.retention_pct is None


def test_a_cohort_whose_window_has_not_elapsed_reports_nothing() -> None:
    """Joined four days ago, so they have not had a week to come back in.
    Calling that 0% makes a healthy launch look like a failing one."""
    signups = {MONDAY: {"a", "b"}}
    cohort = retention(signups, {}, week_start=MONDAY, as_of=MONDAY + timedelta(days=4))

    assert cohort.complete is False
    assert cohort.retention_pct is None


def test_the_window_completing_makes_the_number_real() -> None:
    signups = {MONDAY: {"a", "b"}}
    activity = {MONDAY + timedelta(days=9): {"a"}}
    cohort = retention(signups, activity, week_start=MONDAY, as_of=MONDAY + timedelta(days=21))

    assert cohort.complete is True
    assert cohort.retention_pct == 50.0


def test_users_who_return_the_following_week_are_retained() -> None:
    signups = {MONDAY: {"a", "b"}}
    activity = {MONDAY + timedelta(days=9): {"a"}}

    cohort = retention(signups, activity, week_start=MONDAY)
    assert cohort.signed_up == 2
    assert cohort.returned_week_1 == 1
    assert cohort.retention_pct == 50.0


def test_activity_during_the_signup_week_does_not_count_as_returning() -> None:
    """Coming back is the whole question; using it on day one is not that."""
    signups = {MONDAY: {"a"}}
    activity = {MONDAY + timedelta(days=2): {"a"}}

    assert retention(signups, activity, week_start=MONDAY).returned_week_1 == 0


def test_someone_elses_activity_does_not_flatter_a_cohort() -> None:
    signups = {MONDAY: {"a"}}
    activity = {MONDAY + timedelta(days=9): {"stranger"}}

    assert retention(signups, activity, week_start=MONDAY).returned_week_1 == 0


def test_retention_is_immutable() -> None:
    cohort = Cohort(week_start=MONDAY, signed_up=2, returned_week_1=1)
    with pytest.raises(AttributeError):
        cohort.signed_up = 5  # type: ignore[misc]


# --- the endpoint ----------------------------------------------------------


@pytest.fixture
def admin(monkeypatch: pytest.MonkeyPatch, user_id: uuid.UUID):
    monkeypatch.setenv("ADMIN_USER_IDS", str(user_id))
    get_settings.cache_clear()
    yield {"Authorization": f"Bearer {make_token(user_id)}"}
    get_settings.cache_clear()


def test_metrics_needs_authentication(client: TestClient) -> None:
    assert client.get("/admin/metrics", params={"date": str(MONDAY)}).status_code == 401


def test_a_normal_user_gets_a_404_not_a_403(client: TestClient) -> None:
    """A 403 would confirm the endpoint exists; a 404 says nothing."""
    headers = {"Authorization": f"Bearer {make_token()}"}
    resp = client.get("/admin/metrics", params={"date": str(MONDAY)}, headers=headers)
    assert resp.status_code == 404


def test_an_unset_admin_list_admits_nobody(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unset variable must never mean "everyone"."""
    monkeypatch.setenv("ADMIN_USER_IDS", "")
    get_settings.cache_clear()

    headers = {"Authorization": f"Bearer {make_token()}"}
    assert (
        client.get("/admin/metrics", params={"date": str(MONDAY)}, headers=headers).status_code
        == 404
    )
    get_settings.cache_clear()


def test_an_admin_sees_the_numbers(client: TestClient, admin: dict) -> None:
    body = client.get("/admin/metrics", params={"date": str(MONDAY)}, headers=admin).json()

    assert body["as_of"] == str(MONDAY)
    assert body["total_users"] >= 1
    assert "stickiness_pct" in body
    assert len(body["cohorts"]) == 6


def test_opening_the_dashboard_records_presence(
    client: TestClient, db: Session, admin: dict, user_id: uuid.UUID
) -> None:
    client.get("/dashboard", params={"date": str(MONDAY)}, headers=admin)

    rows = db.query(UserActivity).filter(UserActivity.user_id == user_id).all()
    assert [row.active_on for row in rows] == [MONDAY]


def test_presence_is_recorded_once_a_day_however_often_they_look(
    client: TestClient, db: Session, admin: dict, user_id: uuid.UUID
) -> None:
    for _ in range(5):
        client.get("/dashboard", params={"date": str(MONDAY)}, headers=admin)

    rows = db.query(UserActivity).filter(UserActivity.user_id == user_id).all()
    assert len(rows) == 1


def test_activity_feeds_the_active_counts(client: TestClient, admin: dict) -> None:
    client.get("/dashboard", params={"date": str(MONDAY)}, headers=admin)

    body = client.get("/admin/metrics", params={"date": str(MONDAY)}, headers=admin).json()
    assert body["active_1"] >= 1
    assert body["active_7"] >= 1
