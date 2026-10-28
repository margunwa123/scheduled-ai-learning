# Build from the REPO ROOT (not this folder), since pyproject.toml / uv.lock
# live there:
#   docker build -f langgraph_learning/Dockerfile -t langgraph-learning .
#
# Adapted from uv's official AWS Lambda integration guide:
# https://docs.astral.sh/uv/guides/integration/aws-lambda/

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

# ---- Stage 1: install dependencies into the Lambda task root ----
FROM public.ecr.aws/lambda/python:3.12 AS builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_NO_INSTALLER_METADATA=1
ENV UV_LINK_MODE=copy

RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export --frozen --no-emit-workspace --only-group lambda --no-editable -o requirements.txt && \
    uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# ---- Stage 2: minimal runtime image (no uv binary, no build cache) ----
FROM public.ecr.aws/lambda/python:3.12

COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}
COPY ./langgraph_learning/app ${LAMBDA_TASK_ROOT}/app

# Module app.main, object `handler` (the Mangum-wrapped FastAPI app).
CMD ["app.main.handler"]
