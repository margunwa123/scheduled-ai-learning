"""
Stage 2 ingestion pipeline for the IDX disclosures corpus (langgraph_learning/app/ingestion.py).

Deterministic pipeline, NOT an agent/LangGraph tool (see Stage 1 design notes —
the "who controls the loop" test: no multi-step reasoning here, just one LLM
call for classification).

Flow: dedup check (by filename) -> chunk (Docling) -> classify+summarize
(one Gemini call on the first chunk) -> embed (Voyage) -> store (pgvector).
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import psycopg
import voyageai
from docling.document_converter import DocumentConverter
from dotenv import load_dotenv
from google import genai
from pgvector.psycopg import register_vector

# Reads .env and injects its values into os.environ — without this, nothing
# actually loads the file; load_dotenv() with no args walks up from this
# file's directory looking for .env, so it finds a repo-root .env fine even
# though this file lives two levels down in langgraph_learning/app/.
load_dotenv()

# ---------------------------------------------------------------------------
# Static company metadata for the 7-filing corpus (decided 2026-10-29).
# Best-effort real-world facts pulled from public reporting — verify/correct
# freely, especially GTSI's sector label, before relying on it.
# ---------------------------------------------------------------------------

COMPANY_METADATA = {
    "BBCA": {"company": "PT Bank Central Asia Tbk", "sector": "Banking & Financial Services"},
    "BMRI": {"company": "PT Bank Mandiri (Persero) Tbk", "sector": "Banking & Financial Services"},
    "BBRI": {"company": "PT Bank Rakyat Indonesia (Persero) Tbk", "sector": "Banking & Financial Services"},
    "BUKA": {"company": "PT Bukalapak.com Tbk", "sector": "Technology & E-commerce"},
    "CMRY": {"company": "PT Cisarua Mountain Dairy Tbk", "sector": "Consumer Goods (Dairy/F&B)"},
    "GTSI": {"company": "PT GTS Internasional Tbk", "sector": "Energy & Maritime Logistics (LNG Transport)"},
}

CLASSES = [
    "shareholder_change",
    "volatility_report",
    "financial_report",
    "share_issuance_prospectus",
    "shareholder_meeting",
    "other",
]

EMBEDDING_MODEL = "voyage-4-large"
# Configurable so a model deprecation (like gemini-2.5-flash's, hit 2026-10-29)
# is a .env change, not a code edit.
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", "gemini-3.8-flash")
# Default is 1024 per Voyage's docs (256/512/1024/2048 are the options).
# CONFIRM this matches whatever finance_rag/build_index.py actually used —
# if that pipeline set a custom output_dimension, change this to match.
EMBEDDING_DIM = 1024

DDL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS filing_chunks (
    id             SERIAL PRIMARY KEY,
    doc_id         TEXT NOT NULL,
    company        TEXT NOT NULL,
    sector         TEXT NOT NULL,
    classification TEXT NOT NULL,
    summary        TEXT,
    chunk_index    INT NOT NULL,
    chunk_text     TEXT NOT NULL,
    embedding      VECTOR({EMBEDDING_DIM}) NOT NULL,
    filing_date    DATE,
    UNIQUE (doc_id, chunk_index)
);
"""

INDEX_DDL = """
CREATE INDEX IF NOT EXISTS filing_chunks_embedding_idx
    ON filing_chunks USING hnsw (embedding vector_cosine_ops);
"""


@dataclass
class IngestResult:
    doc_id: str
    status: Literal["ingested", "skipped_duplicate", "failed"]
    detail: str = ""
    n_chunks: int = 0


def get_conn() -> psycopg.Connection:
    # register_vector teaches psycopg how to adapt a Python list/array into
    # the `vector` column type — without this, inserting or comparing against
    # `embedding` either errors outright or needs manual ::vector casting.
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(DDL)
        conn.execute(INDEX_DDL)
        conn.commit()


def _ticker_from_filename(path: Path) -> str:
    stem = path.stem.upper()
    for ticker in COMPANY_METADATA:
        if ticker in stem:
            return ticker
    raise ValueError(f"Could not infer ticker from filename: {path.name}")


def _chunk_document(path: Path) -> list[str]:
    """Docling, logical-item level (paragraph/table) in reading order —
    same approach as finance_rag's parse_filing.py, not per-page text."""
    converter = DocumentConverter()
    result = converter.convert(str(path))
    doc = result.document
    chunks = []
    for item, _level in doc.iterate_items():
        text = getattr(item, "text", None)
        if text and text.strip():
            chunks.append(text.strip())
    return chunks


def _classify_and_summarize(first_chunk: str, client: genai.Client) -> dict:
    """One LLM call, on the first chunk only, returning both the
    classification label and a doc-level summary — cheap by design."""
    prompt = f"""You are classifying an Indonesian stock exchange (IDX) disclosure filing.
Read the excerpt below (the start of the document) and respond with JSON only,
no markdown fences, matching exactly this shape:
{{"classification": "<one of {CLASSES}>", "summary": "<two sentence summary>"}}

Excerpt:
{first_chunk[:4000]}
"""
    response = client.models.generate_content(
        model=CLASSIFIER_MODEL,
        contents=prompt,
    )
    return json.loads(response.text)


def _embed_chunks(vo_client, chunks, batch_size=1000):
    embeddings = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        embeddings.extend(
            vo_client.embed(
                batch, model=EMBEDDING_MODEL,
                input_type="document", output_dimension=EMBEDDING_DIM,
            ).embeddings
        )
    return embeddings

def ingest_filing(
    path: Path, vo_client: voyageai.Client, genai_client: genai.Client
) -> IngestResult:
    doc_id = path.name  # dedup key = filename, per Stage 1 decision

    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM filing_chunks WHERE doc_id = %s LIMIT 1", (doc_id,)
        ).fetchone()
        if exists:
            return IngestResult(doc_id, "skipped_duplicate", "doc_id already in db")

    try:
        ticker = _ticker_from_filename(path)
        meta = COMPANY_METADATA[ticker]

        chunks = _chunk_document(path)
        if not chunks:
            return IngestResult(doc_id, "failed", "no extractable text/chunks")

        classified = _classify_and_summarize(chunks[0], genai_client)
        classification = classified["classification"]
        summary = classified["summary"]

        # input_type="document" asks Voyage for the indexing-side embedding;
        # use input_type="query" on the retrieval side (search_filings) —
        # these are asymmetric and mixing them up hurts retrieval quality.
        embeddings =_embed_chunks(vo_client=vo_client, chunks=chunks, batch_size=1000)

        with get_conn() as conn:
            for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                conn.execute(
                    """
                    INSERT INTO filing_chunks
                        (doc_id, company, sector, classification, summary,
                         chunk_index, chunk_text, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        doc_id,
                        meta["company"],
                        meta["sector"],
                        classification,
                        summary,
                        i,
                        chunk_text,
                        embedding,
                    ),
                )
            conn.commit()

        return IngestResult(doc_id, "ingested", classification, n_chunks=len(chunks))

    except Exception as e:
        return IngestResult(doc_id, "failed", str(e))


def ingest_directory(data_dir: Path) -> list[IngestResult]:
    vo_client = voyageai.Client()
    genai_client = genai.Client()
    return [
        ingest_filing(p, vo_client, genai_client)
        for p in sorted(data_dir.glob("*.pdf"))
    ]


def print_report(results: list[IngestResult]) -> None:
    for r in results:
        print(f"[{r.status.upper():17}] {r.doc_id} — {r.detail} ({r.n_chunks} chunks)")


if __name__ == "__main__":
    init_db()
    results = ingest_directory(Path(__file__).parent.parent / "data")
    print_report(results)