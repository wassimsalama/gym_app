# Single-stage: the dependency set is small and the image rebuilds rarely, so a
# multi-stage build would trade readability for a few tens of megabytes.
FROM python:3.12-slim

# Bytecode is written at build time instead of on every cold start, and Python
# never buffers logs — Railway shows them live rather than in bursts.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies are copied and installed before the source, so editing a router
# does not invalidate the layer that pip populated.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic ./alembic

# Run as a non-root user. Nothing here needs privileges, and a container that
# never needs them should never have them.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Railway (and most hosts) inject the port to listen on.
ENV PORT=8000
EXPOSE 8000

# Migrations run before the server accepts traffic, so a deploy can never serve
# requests against a schema it does not expect. Alembic is idempotent, so a
# restart with nothing to do costs a query.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
