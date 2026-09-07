# Built with the *repository root* as context, because that is what Railway and
# most hosts do. Every COPY path is therefore relative to the repo root, not to
# this file's directory — building with `api/` as the context will not work, and
# was how this originally shipped broken.
#
#   docker build -f api/Dockerfile -t gym-api .
#
# Single-stage on purpose: the dependency set is small and this rebuilds rarely,
# so multi-stage would trade readability for a few tens of megabytes.
FROM python:3.12-slim

# Bytecode is written at build time rather than on every cold start, and Python
# never buffers logs — the host shows them live instead of in bursts.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies before source, so editing a router does not invalidate the layer
# pip populated.
COPY api/pyproject.toml ./
COPY api/app ./app
RUN pip install --no-cache-dir .

COPY api/alembic.ini ./
COPY api/alembic ./alembic

# Nothing here needs privileges, so it does not get any.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Railway and friends inject the port to listen on.
ENV PORT=8000
EXPOSE 8000

# Migrations run before the server accepts traffic, so a deploy can never serve
# requests against a schema it does not expect. Alembic is idempotent, so a
# restart with nothing to do costs one query.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
