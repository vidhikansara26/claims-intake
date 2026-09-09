FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY data ./data
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "claims.api.routes:app", "--host", "0.0.0.0", "--port", "8000"]