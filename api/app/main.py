from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
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
    title="Gym App API",
    version="0.1.0",
    description=(
        "Nutrition, training, weight, recovery and progress data — plus the "
        "evidence-based suggestions engine derived from them."
    ),
)

if settings.origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router)
app.include_router(daily_logs.router)
app.include_router(goals.router)
app.include_router(dashboard.router)
app.include_router(exercises.router)
app.include_router(workout_sessions.router)
app.include_router(photos.router)
app.include_router(account.router)
