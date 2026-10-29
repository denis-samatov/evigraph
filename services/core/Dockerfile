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

RUN groupadd --system --gid 10001 evigraph \
    && useradd --system --uid 10001 --gid 10001 --create-home evigraph \
    && mkdir -p /data/artifacts \
    && chown -R evigraph:evigraph /data

ENV EVIGRAPH_ARTIFACT_DIR=/data/artifacts PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/uv-cache
USER 10001:10001
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "evigraph-core", "serve", "--host", "0.0.0.0", "--port", "8000"]
