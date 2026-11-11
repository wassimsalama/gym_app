"""Step-count summaries.

Every function here skips days with no step count rather than treating them as
zero. That is the whole point of the column being nullable: a day someone forgot
to sync their phone is a day we know nothing about, and averaging it as zero
would understate activity and feed a false observation into the suggestions
engine — which tells people things about their own health.
"""

from dataclasses import dataclass

#: Days of history the rolling average looks back over.
WINDOW_DAYS = 7

#: Below this many logged days the average is shown but marked unreliable, the
#: same threshold idea as the TDEE estimate: two days is not a habit.
MIN_DAYS_FOR_AVERAGE = 3


@dataclass(frozen=True)
class StepSummary:
    """`average` is None when nothing in the window was logged at all."""

    today: int | None
    average: int | None
    days_logged: int
    reliable: bool


def summarise(values: list[int | None], today_value: int | None) -> StepSummary:
    """Average the logged days in the window, ignoring the rest.

    `values` is the window oldest-first; `None` entries are days with no count.
    """
    logged = [v for v in values if v is not None]

    if not logged:
        return StepSummary(today=today_value, average=None, days_logged=0, reliable=False)

    return StepSummary(
        today=today_value,
        average=round(sum(logged) / len(logged)),
        days_logged=len(logged),
        reliable=len(logged) >= MIN_DAYS_FOR_AVERAGE,
    )
