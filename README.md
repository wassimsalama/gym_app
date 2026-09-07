# Gym App

Nutrition, training, weight, recovery and progress photos in one place — and
evidence-based suggestions derived from the combination.

> **Status: Phase 0 complete.** Backend, schema, auth and the app shell are in
> place. Weight logging lands in Phase 1. See the [roadmap](#roadmap).

## The problem

Fitness apps die from logging fatigue. Every one of them asks for more than a
person will actually give on a Tuesday in February, and the moment a streak
breaks the app becomes a monument to failure.

This one collects a deliberately small set of high-signal inputs — daily weight,
daily macros, lightweight workout logs — and derives everything else: TDEE,
goal projections, plateau detection, PRs, streaks. Every logging interaction is
built to finish in under 15 seconds.

The differentiator is correlation across streams. A stalled bench press is not
a training problem when the same fortnight shows a 400 kcal daily deficit, and
the app says so with the numbers attached:

> Bench stalled 4 sessions. Your average intake is ~400 kcal under maintenance
> over the same period — likely diet-related, not a training problem.

No generic praise strings. Every suggestion carries its evidence.

## Architecture

```
┌─────────────────────────────────────┐
│  Expo app (React Native, TS)        │
│  expo-router · NativeWind           │
│  offline queue (SQLite)             │
└───────────────┬─────────────────────┘
                │ HTTPS + Supabase JWT
                ▼
┌─────────────────────────────────────┐
│  FastAPI (Python 3.12)              │
│  ├── routers/   parse · authz       │
│  └── services/  the engine ─────────┼──▶ pure Python, no ORM types,
└───────────────┬─────────────────────┘     unit-tested in isolation
                │ SQLAlchemy 2.0
                ▼
┌─────────────────────────────────────┐
│  PostgreSQL 16                      │
└─────────────────────────────────────┘

  Photos bypass the API entirely: the app PUTs and GETs a private S3
  bucket through presigned URLs. Image bytes never touch the backend.
```

Some load-bearing choices:

- **kg is canonical** in the database and across the API. Conversion to the
  user's display unit happens in exactly one file, `app/lib/units.ts`.
- **Nothing derived is stored.** No `is_pr` column, no cached TDEE, no streak
  counter — they would go stale. Services compute them from the log tables.
- **The API is stateless, and holds no signing secret.** Supabase issues the
  session; FastAPI verifies each request's JWT against the project's *public*
  keys (JWKS, ES256). A leaked backend environment cannot forge a token.
- **Local dates, not UTC.** The client sends the date its own clock shows, so a
  9pm workout in a western timezone lands on the right day.

## Stack

| Layer    | Choice                                                  |
| -------- | ------------------------------------------------------- |
| App      | Expo SDK 57, React Native 0.86, TypeScript, expo-router  |
| Styling  | NativeWind (Tailwind)                                   |
| Auth     | Supabase Auth (email/password), ES256 JWT verified via JWKS |
| API      | FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic           |
| Database | PostgreSQL 16                                           |
| Photos   | S3, private bucket, presigned URLs both directions      |
| CI       | GitHub Actions — ruff, pytest, tsc, eslint, prettier    |

## Running it

**Prerequisites:** Docker, Python 3.12, Node 20, and a Supabase project.

### 1. Database

```bash
docker compose up -d
```

### 2. API

```bash
cd api
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
cp .env.example .env          # add your SUPABASE_URL
./.venv/bin/alembic upgrade head
```

Seed the exercise catalogue (876 exercises from
[free-exercise-db](https://github.com/yuhonas/free-exercise-db); idempotent, so
re-running is safe):

```bash
./.venv/bin/python ../scripts/seed_exercises.py
```

Serve it on your LAN, not just localhost — a phone cannot reach `localhost`:

```bash
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. App

```bash
cd app
npm install
cp .env.example .env
```

Fill in `app/.env`. `EXPO_PUBLIC_API_URL` must be your laptop's LAN IP with the
phone on the same Wi-Fi:

```bash
ipconfig getifaddr en0        # -> e.g. 192.168.1.42
```

```bash
npm start                     # scan the QR code with Expo Go
```

### Checks

```bash
cd api && ./.venv/bin/ruff check . && ./.venv/bin/pytest && ./.venv/bin/alembic check
cd app && npm run typecheck && npm run lint && npm run format:check
```

## Layout

```
gym-app/
├── app/                  Expo application
│   ├── app/              expo-router routes — (auth) and (tabs)
│   ├── components/       reusable UI
│   └── lib/              api · auth · units · dates  (sync in Phase 2)
├── api/
│   └── app/
│       ├── core/         settings, DB session, JWT dependency
│       ├── models/       SQLAlchemy 2.0 models
│       ├── routers/      parse · authorize · delegate — no business logic
│       └── services/     the engine — smoothing, projection, stats
├── scripts/              exercise seeding
└── .github/workflows/    CI
```

## Roadmap

| Phase | Scope                                                    | State |
| ----- | -------------------------------------------------------- | ----- |
| 0     | Scaffold, schema, auth end-to-end, CI                    | done  |
| 1     | Weight loop — entry, smoothed trend, goals, onboarding   | done  |
| 2     | Workout logging, last-set prefill, PRs, offline queue    | next  |
| 3     | Nutrition, streaks, volume rings, TDEE, dashboard        |       |
| 4     | Photos, suggestions engine, recap, TestFlight, App Store |       |

Decisions made along the way are logged in [DECISIONS.md](DECISIONS.md).
