FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN uv sync --frozen --no-dev

ENV EVIGRAPH_ARTIFACT_DIR=/data/artifacts
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync evigraph-core migrate && uv run --no-sync evigraph-core serve --host 0.0.0.0 --port 8000"]
