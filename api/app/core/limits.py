"""Applying rate limits to requests.

Two layers, because they catch different things:

* per client address — the only defence before a caller has identified itself,
  and what stops unauthenticated flooding.
* per user — a signed-in account that starts hammering is still a problem, and
  one that has already passed the address check.

Both must be generous enough that the offline queue's legitimate retries never
trip them (§8), which is why the numbers are in the hundreds per hour.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.core.ratelimit import Decision, Limit, limiter
from app.models import Profile


def client_address(request: Request, settings: Settings) -> str:
    """Best available identifier for the caller.

    `X-Forwarded-For` is only consulted when the deployment says a proxy is in
    front, because otherwise a client can set it to anything and give itself an
    unlimited supply of fresh identities.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Left-most entry is the original client; the rest are proxies.
            return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


def _enforce(decision: Decision, limit: Limit) -> None:
    if decision.allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many requests. The limit is {limit.description}.",
        # The client waits this out rather than guessing, and the sync queue
        # uses it instead of its own backoff.
        headers={"Retry-After": str(decision.retry_after)},
    )


def limit_by_address(request: Request) -> None:
    """Applied to every route, signed in or not."""
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    limit = Limit(max_requests=settings.rate_limit_ip_per_hour, window_seconds=3600)
    _enforce(limiter.check(f"ip:{client_address(request, settings)}", limit), limit)


def _limit_user(user: Profile, bucket: str, max_per_hour: int) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    limit = Limit(max_requests=max_per_hour, window_seconds=3600)
    _enforce(limiter.check(f"{bucket}:{user.id}", limit), limit)


def limit_reads(user: CurrentUser) -> Profile:
    _limit_user(user, "read", get_settings().rate_limit_read_per_hour)
    return user


def limit_writes(user: CurrentUser) -> Profile:
    _limit_user(user, "write", get_settings().rate_limit_write_per_hour)
    return user


#: Drop-in replacements for `CurrentUser` on routes that read or write.
ReadUser = Annotated[Profile, Depends(limit_reads)]
WriteUser = Annotated[Profile, Depends(limit_writes)]
