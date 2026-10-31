"""
Agent-callable tools for the IDX research agent (langgraph_learning/app/tools.py).

Unlike ingestion.py, these ARE invoked by the LangGraph ReAct loop — each
@tool-decorated function is something the model can choose to call at a
given reasoning step, per the Stage 1 tool-surface design.
"""

from typing import Optional

import voyageai
from langchain_core.tools import tool
from langgraph.types import interrupt

from .ingestion import EMBEDDING_DIM, EMBEDDING_MODEL, get_conn

_vo_client = voyageai.Client()


def _embed_query(text: str) -> list:
    # input_type="query" — the other half of the asymmetric pair: ingestion
    # used input_type="document". Mixing these up silently degrades retrieval
    # quality rather than erroring, so it's easy to miss if you forget it.
    return _vo_client.embed(
        [text],
        model=EMBEDDING_MODEL,
        input_type="query",
        output_dimension=EMBEDDING_DIM,
    ).embeddings[0]


# ---------------------------------------------------------------------------
# Research tools — no confirmation needed, nothing destructive.
# ---------------------------------------------------------------------------


@tool
def search_filings(
    query: str,
    sector: Optional[str] = None,
    classification: Optional[str] = None,
    company: Optional[str] = None,
    k: int = 5,
) -> list[dict]:
    """Semantic search over ingested IDX filings. Optionally filter by sector,
    classification (shareholder_change/volatility_report/financial_report/
    share_issuance_prospectus/shareholder_meeting/other), or company. Returns
    the top-k matching chunks with their source metadata for citation."""
    embedding = _embed_query(query)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT doc_id, company, sector, classification, summary,
                   chunk_index, chunk_text, embedding <-> %(embedding)s AS distance
            FROM filing_chunks
            WHERE (%(sector)s IS NULL OR sector = %(sector)s)
              AND (%(classification)s IS NULL OR classification = %(classification)s)
              AND (%(company)s IS NULL OR company = %(company)s)
            ORDER BY distance
            LIMIT %(k)s
            """,
            {
                "embedding": embedding,
                "sector": sector,
                "classification": classification,
                "company": company,
                "k": k,
            },
        ).fetchall()
    cols = ["doc_id", "company", "sector", "classification", "summary",
            "chunk_index", "chunk_text", "distance"]
    return [dict(zip(cols, r)) for r in rows]


@tool
def get_company_filings(company: str) -> list[dict]:
    """List every filing on record for a given company (full name), with its
    classification, filing date, and summary — one row per document, not
    per chunk."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT doc_id, classification, filing_date, summary
            FROM filing_chunks
            WHERE company = %s
            ORDER BY filing_date
            """,
            (company,),
        ).fetchall()
    cols = ["doc_id", "classification", "filing_date", "summary"]
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# Corpus management — dual-exposed: a plain function the CLI calls directly
# (no confirmation needed; the CLI invocation IS the human asking), and an
# @tool wrapper the agent can call from natural language.
# ---------------------------------------------------------------------------


def list_sources() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT doc_id, company, classification, filing_date
            FROM filing_chunks
            ORDER BY company, filing_date
            """
        ).fetchall()
    cols = ["doc_id", "company", "classification", "filing_date"]
    return [dict(zip(cols, r)) for r in rows]


@tool
def list_sources_tool() -> list[dict]:
    """Show what filings currently exist in the corpus."""
    return list_sources()


def delete_source(doc_id: str) -> int:
    """Delete a filing and all its chunks. Returns the number of chunk rows removed."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM filing_chunks WHERE doc_id = %s", (doc_id,))
        conn.commit()
        return cur.rowcount


@tool
def delete_source_tool(doc_id: str) -> str:
    """Delete a filing and all its chunks from the corpus. Destructive —
    pauses for human confirmation before executing anything."""
    # interrupt() pauses the graph here and surfaces this payload to whatever
    # is running it (the terminal REPL). Resuming with Command(resume=...)
    # continues execution from this exact point with that value bound to
    # `decision` below. Requires the graph to be compiled with a checkpointer
    # (e.g. MemorySaver) — wired in when we build agent.py next.
    decision = interrupt(
        {
            "action": "delete_source",
            "doc_id": doc_id,
            "message": f"Agent wants to delete '{doc_id}' and all its chunks. Confirm? (yes/no)",
        }
    )
    if decision != "yes":
        return f"Deletion of '{doc_id}' was not confirmed; nothing was deleted."
    n = delete_source(doc_id)
    return f"Deleted {n} chunk(s) for '{doc_id}'."