"""FastAPI app wrapping the LangGraph agent, deployed to Cloud Run.

Cloud Run routes plain HTTP traffic straight to a container listening on
$PORT, so this is an ordinary FastAPI app served by uvicorn -- no adapter
layer needed (unlike Lambda, which required Mangum to translate its event
format into an ASGI request).
"""

from fastapi import FastAPI
from pydantic import BaseModel

from app.agent import run_agent

app = FastAPI(title="langgraph_learning agent (Section 6 deployment scaffold)")


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    answer: str


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    answer = run_agent(req.query)
    return QueryResponse(answer=answer)
