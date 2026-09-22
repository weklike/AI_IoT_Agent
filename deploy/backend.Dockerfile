FROM python:3.12.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend backend
COPY simulator simulator
COPY tests/__init__.py tests/__init__.py
COPY tests/support tests/support
RUN uv sync --locked --no-dev
CMD ["/app/.venv/bin/uvicorn", "backend.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
