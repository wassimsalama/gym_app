"""Step summaries — chiefly, that unlogged days are not zeros."""

from app.services import steps


def test_no_data_gives_no_average() -> None:
    summary = steps.summarise([None, None], today_value=None)

    assert summary.average is None
    assert summary.days_logged == 0
    assert summary.reliable is False


def test_unlogged_days_are_skipped_not_counted_as_zero() -> None:
    """The bug this whole design exists to prevent.

    Two logged days of 10000 average 10000. If the five unlogged days in the
    window counted as zero the answer would be 2857 — a number that would make
    an active person look sedentary, and which the suggestions engine would then
    say something about.
    """
    window = [None, None, 10_000, None, None, 10_000, None]

    summary = steps.summarise(window, today_value=None)

    assert summary.average == 10_000
    assert summary.days_logged == 2


def test_a_logged_zero_does_count() -> None:
    """0 is a fact; None is the absence of one. They must not behave the same."""
    assert steps.summarise([10_000, 0], today_value=0).average == 5_000
    assert steps.summarise([10_000, None], today_value=None).average == 10_000


def test_the_average_is_unreliable_until_there_are_enough_days() -> None:
    assert steps.summarise([8_000, 9_000], today_value=None).reliable is False
    assert steps.summarise([8_000, 9_000, 10_000], today_value=None).reliable is True


def test_today_is_reported_separately_from_the_average() -> None:
    summary = steps.summarise([4_000, 6_000], today_value=12_000)

    assert summary.today == 12_000
    assert summary.average == 5_000
