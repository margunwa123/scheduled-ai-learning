"""FastAPI app wrapping the LangGraph agent, adapted to Lambda via Mangum.

Mangum translates the API Gateway / Lambda Function URL event into an ASGI
request FastAPI understands, and translates the response back -- so this is
an ordinary FastAPI app everywhere except the last line.
"""

from fastapi import FastAPI
from mangum import Mangum
from pydantic import BaseModel
from dotenv import load_dotenv

from app.agent import run_agent

load_dotenv()

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


# Lambda's CMD points at "app.main.handler" -- this is that object.
handler = Mangum(app)
