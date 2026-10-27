# langgraph_learning (Phase 5, Section 6 deployment scaffold)

Throwaway ReAct agent (a real calculator tool + a stub "stock price" tool,
clearly labeled fake) whose only job is to prove out the Docker + Lambda
deployment path. Section 7 swaps `app/agent.py`'s tools and model prompt for
the real IDX multi-agent graph; `app/main.py`'s FastAPI/Mangum wiring and the
Dockerfile don't need to change.

## 1. Add dependencies (run from the repo root)

```
uv add langgraph langchain-google-genai fastapi mangum
uv add --dev uvicorn  # local testing only, not needed inside the Lambda image
```

## 2. Test locally first, before touching Docker

```
export GEMINI_API_KEY=...        # same key you've used for Gemini elsewhere
# --app-dir makes `app` a top-level package, matching the layout inside the
# image (where app/ sits at ${LAMBDA_TASK_ROOT}), so `from app.agent import ...`
# resolves identically here and on Lambda.
uv run uvicorn app.main:app --reload --app-dir langgraph_learning
```

Then: `curl -s localhost:8000/ ` for the health check, and
`curl -s -X POST localhost:8000/query -H 'content-type: application/json' -d '{"query": "What is 12.5 * 3, and what is the stub price for BBCA?"}'`
to confirm the agent actually picks both tools.

## 3. Build the container (from the repo root, not this folder)

```
docker build -f langgraph_learning/Dockerfile -t langgraph-learning .
```

## 4. Run the built image locally against the Lambda Runtime Interface Emulator

AWS's base image includes the emulator automatically when you `docker run`
it (it listens on port 8080 inside the container):

```
docker run --rm -p 9000:8080 -e GEMINI_API_KEY=... langgraph-learning
```

Then from another terminal, invoke it the way Lambda's runtime would (this is
NOT a normal HTTP call to your FastAPI routes -- it's the Lambda invoke
wrapper, which is why the URL looks different from step 2):

```
curl -s -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -d '{"version":"2.0","routeKey":"POST /query","rawPath":"/query","requestContext":{"http":{"method":"POST","path":"/query"}},"body":"{\"query\":\"What is 9 * 9?\"}","isBase64Encoded":false}'
```

If that returns a proper JSON answer, the container behaves correctly under
Lambda's actual invocation model -- not just under plain uvicorn -- before
you've spent anything pushing it to AWS.

## Next (not yet done here)

Lambda runs container images from **Amazon ECR**, not from a local Docker
build directly -- the remaining steps are: create an ECR repository, tag and
push this image to it, then create the Lambda function pointing at that image
URI, with `GEMINI_API_KEY` set via Lambda's environment variables sourced from
Secrets Manager (not a plaintext env var) per the Section 6 secrets note.
Natural next step once this builds and runs clean locally.
