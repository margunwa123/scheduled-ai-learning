import sys
import uuid
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from .agent import _extract_text, graph
from .ingestion import get_conn
from .tools import delete_source, list_sources

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# 1) Ask the agent
# ---------------------------------------------------------------------------


def cmd_ask() -> None:
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    print("\nAsk the IDX research agent. Type 'back' to return to the menu.\n")

    while True:
        query = input("> ").strip()
        if not query:
            continue
        if query.lower() in ("back", "exit", "quit"):
            return

        result = graph.invoke(
            {
                "messages": [HumanMessage(content=query)],
                "critic_verdict": None,
                "critic_reasoning": None,
                "critic_retries": 0,
            },
            config=config,
        )
        _drain_interrupts(result, config)


def _drain_interrupts(result: dict, config: dict) -> None:
    # NOTE: I haven't run this against your installed langgraph version, so
    # treat the "__interrupt__" key name as the thing most likely to need a
    # fix here — check it against whatever your version's invoke() actually
    # returns on a paused run, the same way you checked the embed() batch
    # limit instead of trusting the docstring.
    while result.get("__interrupt__"):
        payload = result["__interrupt__"][0].value
        print(f"\n[confirm needed] {payload['message']}")
        answer = input("yes/no > ").strip().lower()
        result = graph.invoke(Command(resume=answer), config=config)

    final = result["messages"][-1]
    # final.content can be a plain string or a list of content parts
    # (Gemini via langchain_google_genai sometimes returns the latter) --
    # print the raw object here and you get a messy Python repr instead of
    # the actual generated text, which is the bug that prompted this fix.
    print(f"\n{_extract_text(final.content)}\n")


# ---------------------------------------------------------------------------
# 2) List ingested sources
# ---------------------------------------------------------------------------


def cmd_list_sources() -> None:
    rows = list_sources()
    if not rows:
        print("\nNo filings ingested yet.\n")
        return
    print()
    for r in rows:
        print(
            f"  {r['doc_id']:<32} {r['classification']:<24} {r['company']}  ({r['filing_date']})"
        )
    print()


# ---------------------------------------------------------------------------
# 3) Corpus status — cross-check data/ against Postgres, with chunk counts.
#    This is the exact empirical check from the batch-limit debugging
#    session, promoted from a one-off SQL query into the CLI.
# ---------------------------------------------------------------------------


def cmd_corpus_status() -> None:
    on_disk = {p.name for p in DATA_DIR.glob("*.pdf")}
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT doc_id, count(*) FROM filing_chunks GROUP BY doc_id ORDER BY doc_id"
        ).fetchall()
    ingested = {doc_id: n for doc_id, n in rows}

    print(f"\n{len(on_disk)} PDF(s) in data/, {len(ingested)} doc_id(s) in Postgres.\n")
    for name in sorted(on_disk):
        n = ingested.get(name)
        tag = "OK" if n else "MISSING"
        detail = f"{n} chunks" if n else "not ingested — run ingestion.py"
        print(f"  [{tag:<7}] {name:<40} {detail}")

    orphans = set(ingested) - on_disk
    if orphans:
        print("\nIn Postgres but not in data/ (renamed or removed source file?):")
        for name in sorted(orphans):
            print(f"  {name} ({ingested[name]} chunks)")
    print()


# ---------------------------------------------------------------------------
# 4) Delete a source — direct, no confirmation. The CLI invocation itself
#    is the human asking; the interrupt() gate in delete_source_tool is
#    only for when the *agent* decides to call it from natural language.
# ---------------------------------------------------------------------------


def cmd_delete_source() -> None:
    doc_id = input("\ndoc_id to delete: ").strip()
    if not doc_id:
        return
    n = delete_source(doc_id)
    if n:
        print(f"Deleted {n} chunk(s) for '{doc_id}'.\n")
    else:
        print(f"No rows found for doc_id '{doc_id}'.\n")


# ---------------------------------------------------------------------------
# menu
# ---------------------------------------------------------------------------

MENU = """
IDX research agent
  1) Ask the agent
  2) List ingested sources
  3) Corpus status (data/ vs Postgres)
  4) Delete a source
  0) Exit
"""


def main() -> None:
    while True:
        print(MENU)
        choice = input("> ").strip()
        if choice == "1":
            cmd_ask()
        elif choice == "2":
            cmd_list_sources()
        elif choice == "3":
            cmd_corpus_status()
        elif choice == "4":
            cmd_delete_source()
        elif choice == "0":
            sys.exit(0)
        else:
            print("Unknown option.\n")


if __name__ == "__main__":
    main()
