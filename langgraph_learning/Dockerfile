# Build from the REPO ROOT (not this folder), since pyproject.toml / uv.lock
# live there:
#   docker build -f langgraph_learning/Dockerfile -t langgraph-learning .
#
# Cloud Run runs a plain HTTP container -- no Lambda-style event adapter or
# task-root convention needed, so this installs into a normal venv-free
# site-packages dir and runs uvicorn directly.

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

# ---- Stage 1: install dependencies ----
FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_NO_INSTALLER_METADATA=1
ENV UV_LINK_MODE=copy

RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export --frozen --no-emit-workspace --only-group deploy --no-editable -o requirements.txt && \
    uv pip install -r requirements.txt --target /app

# ---- Stage 2: minimal runtime image ----
FROM python:3.12-slim

COPY --from=builder /app /app
COPY ./langgraph_learning/app /app/app

WORKDIR /app
ENV PYTHONPATH=/app
# Cloud Run sets $PORT (default 8080) and expects the container to listen
# on it -- no fixed port convention like Lambda's task-root/handler shape.
# `python -m uvicorn` (not the `uvicorn` script) because `uv pip install
# --target` drops console scripts under /app/bin, which isn't on $PATH --
# running it as a module avoids depending on that at all.
CMD exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
