"""Engine constants that are product decisions rather than implementation
details, gathered in one file so they can be changed without hunting (§7.6).

Spec §7.6 notes these become user-configurable later; keeping them here is what
makes that a small change.
"""

#: Weekly set targets per muscle group.
#:
#: Ten hard sets a week is the commonly cited lower bound for growth in the big
#: groups. Arms, calves and core get six: they take indirect volume from pressing
#: and pulling, so counting only direct work overstates what they need.
DEFAULT_WEEKLY_SET_TARGETS: dict[str, int] = {
    "chest": 10,
    "back": 10,
    "quads": 10,
    "hamstrings": 10,
    "shoulders": 10,
    "glutes": 10,
    "biceps": 6,
    "triceps": 6,
    "calves": 6,
    "core": 6,
}

#: Groups without a target are still counted, just not held to one.
UNTARGETED_GROUPS = ("other",)

#: Rolling window for the streak counters (§2.1).
#:
#: Deliberately a rolling count rather than a consecutive-day streak: a streak
#: that resets to zero turns one missed day into a reason to stop entirely.
STREAK_WINDOW_DAYS = 14
