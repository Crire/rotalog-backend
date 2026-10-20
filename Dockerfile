FROM ghcr.io/astral-sh/uv:0.13.2 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --locked --no-dev && groupadd -g 10001 rotalog && useradd -r -u 10001 -g rotalog rotalog
USER 10001:10001
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "rotalog.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
