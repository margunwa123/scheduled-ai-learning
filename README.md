# AI Engineer Roadmap

A personal, hands-on learning project working through AI engineering end to
end: embeddings and vector search, retrieval-augmented generation, raw LLM
API usage, agentic systems, and deployment. Each folder is a self-contained
exploration of one topic, built by actually building something rather than
just reading about it.

## What's in here

- **[`qdrant_learning/`](qdrant_learning/)** — Vector search fundamentals with
  Qdrant, built around a "describe a movie, find it" semantic search project:
  embeddings, payload filtering, faceting, query-by-example recommendations,
  and collection updates.
- **[`llamaindex_learning/`](llamaindex_learning/)** — RAG with LlamaIndex
  over a Postgres/pgvector store, including prompt template design for
  grounded Q&A.
- **[`finance_rag/`](finance_rag/)** — RAG applied to real financial filings
  (10-Ks from Apple, Coca-Cola, Southwest Airlines): PDF parsing with Docling
  and a self-chunking strategy using LlamaIndex and Voyage embeddings.
- **[`gemini/`](gemini/)** — Direct usage of the Gemini API outside of a
  framework, including a small ticket-routing client/server example.
- **[`langgraph_learning/`](langgraph_learning/)** — Agentic AI with
  LangGraph (a ReAct agent with real and stubbed tools), plus the deployment
  mechanics around it: containerizing with Docker and shipping to a cloud
  platform (currently Google Cloud Run) behind a public HTTPS endpoint, with
  secrets kept out of both the image and the repo.

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/) as a single
project at the repo root (not per-folder):

```bash
make setup   # installs python3-venv/pip if missing, installs uv, runs `uv sync`
```

Copy `.env.example` to `.env` and fill in the API keys/credentials each
subfolder needs (Gemini, Voyage, Postgres).

Some folders (`qdrant_learning/`, `llamaindex_learning/`) bring up supporting
services via their own `docker-compose.yml`. `langgraph_learning/` has its
own [README](langgraph_learning/README.md) covering its container build and
deploy flow.
