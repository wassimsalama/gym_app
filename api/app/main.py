from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.limits import limit_by_address
from app.routers import (
    account,
    daily_logs,
    dashboard,
    exercises,
    goals,
    health,
    photos,
    workout_sessions,
)

settings = get_settings()

app = FastAPI(
    # Applied to every route, signed in or not — the only defence that works
    # before a caller has identified itself.
    dependencies=[Depends(limit_by_address)],
    title="Gym App API",
    version="0.1.0",
    description=(
        "Nutrition, training, weight, recovery and progress data — plus the "
        "evidence-based suggestions engine derived from them."
    ),
)

# The app runs in a browser, so every request is subject to CORS — a rule that
# simply does not exist on native, which is why this went unnoticed until the
# web build. Without it the browser blocks each call before it is sent, and the
# client can only report "could not reach the server".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_origin_regex=settings.dev_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # So the client can honour rate limiting rather than guessing at it.
    expose_headers=["Retry-After"],
)

app.include_router(health.router)
app.include_router(daily_logs.router)
app.include_router(goals.router)
app.include_router(dashboard.router)
app.include_router(exercises.router)
app.include_router(workout_sessions.router)
app.include_router(photos.router)
app.include_router(account.router)
