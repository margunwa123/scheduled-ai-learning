# langgraph_learning (Phase 5, Section 6 deployment scaffold)

Throwaway ReAct agent (a real calculator tool + a stub "stock price" tool,
clearly labeled fake) whose only job is to prove out the Docker + Cloud Run
deployment path. Section 7 swaps `app/agent.py`'s tools and model prompt for
the real IDX multi-agent graph; `app/main.py`'s FastAPI wiring and the
Dockerfile don't need to change.

## 1. Add dependencies (run from the repo root)

```
uv add --group deploy langgraph langchain-google-genai fastapi uvicorn
```

`uvicorn` is a real runtime dependency here, not a local-only convenience --
Cloud Run runs it directly as the production server, there's no Lambda-style
event adapter in between.

## 2. Test locally first, before touching Docker

```
export GEMINI_API_KEY=...        # same key you've used for Gemini elsewhere
# --app-dir makes `app` a top-level package, matching the layout inside the
# image, so `from app.agent import ...` resolves identically here and deployed.
uv run uvicorn app.main:app --reload --app-dir langgraph_learning
```

Then: `curl -s localhost:8000/ ` for the health check, and
`curl -s -X POST localhost:8000/query -H 'content-type: application/json' -d '{"query": "What is 12.5 * 3, and what is the stub price for BBCA?"}'`
to confirm the agent actually picks both tools.

## 3. Build the container (from the repo root, not this folder)

```
docker build -f langgraph_learning/Dockerfile -t langgraph-learning .
```

## 4. Run the built image locally exactly as Cloud Run would

Cloud Run routes plain HTTP to a container listening on `$PORT` -- no event
envelope, no invocation wrapper, so a local `docker run` is already an
accurate simulation of production behavior:

```
docker run --rm -p 8080:8080 -e GEMINI_API_KEY=... -e PORT=8080 langgraph-learning
```

Then from another terminal, hit the routes directly, same as step 2:

```
curl -s localhost:8080/
curl -s -X POST localhost:8080/query -H 'content-type: application/json' -d '{"query": "What is 9 * 9?"}'
```

## Next (not yet done here)

Cloud Run runs container images from **Artifact Registry**, not from a local
Docker build directly -- the remaining steps are: create an Artifact
Registry repository, tag and push this image to it, then deploy to Cloud Run
pointing at that image, with `GEMINI_API_KEY` wired in from Secret Manager
(not a plaintext env var) per the Section 6 secrets note. Natural next step
once this builds and runs clean locally.
