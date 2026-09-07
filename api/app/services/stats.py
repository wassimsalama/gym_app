"""Small numeric helpers shared by the engine.

Kept dependency-free on purpose: the engine is plain Python over plain data, so
it stays trivially unit-testable and cheap to reason about.
"""


def least_squares_slope(xs: list[float], ys: list[float]) -> float | None:
    """Ordinary least-squares slope of y over x.

    Returns None when the slope is undefined — fewer than two points, or every
    x identical (a vertical line has no slope).
    """
    n = len(xs)
    if n != len(ys) or n < 2:
        return None

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denominator = sum((x - mean_x) ** 2 for x in xs)

    if denominator == 0:
        return None
    return numerator / denominator
