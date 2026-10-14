"""
MCP server for the Support Ticket Router milestone project (Phase 3, Section 5).

This is the "kitchen" from the restaurant analogy: it exposes one real
capability and does the actual work. It never talks to Gemini and never
decides anything -- it just responds when the client calls it.

Exposes one tool, `route_ticket`, which a client calls once it has already
decided (via the model) that a ticket should be routed somewhere. This
server does the real work: appending the routing decision to a local
"queue" file.

What's MCP-specific here (worth studying) vs. what's just app logic:
  - The `@mcp.tool()` decorator + the function's type hints and docstring
    are what make this tool show up in the DISCOVERY step -- the client
    never has to be told about `route_ticket` by hand. The SDK builds the
    schema from the signature + docstring automatically.
  - `mcp.run()` is what makes this process speak the MCP protocol over
    stdin/stdout once your client spawns it (stdio is the default
    transport when you call it with no arguments).
  - Everything inside `route_ticket`'s body (the JSON-lines append) is
    ordinary Python -- nothing about it is MCP-specific.

Setup (current mcp package, 2.x line, as of Oct 2026):
    pip install "mcp[cli]"

You generally won't run this file directly and expect much to happen --
`mcp.run()` blocks, waiting on stdio for a client to talk to it. Your
client script will spawn it as a subprocess. If you want to poke at it
standalone first, the MCP Inspector can do that:
    uv run mcp dev ticket_router_server.py
(needs npx/Node available, since the Inspector itself is a small Node app)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from mcp.server import MCPServer

QUEUE_FILE = Path(__file__).parent / "ticket_queue.jsonl"

mcp = MCPServer("ticket-router")


@mcp.tool()
def route_ticket(category: str, urgency: str, ticket_id: str) -> dict:
    """Route a classified support ticket to the correct queue.

    Call this once a ticket has been classified and you've decided it
    needs to be routed -- i.e. it's not a duplicate of an existing open
    ticket, and enough information was extracted to act on it.

    Args:
        category: The ticket's category, e.g. "billing", "technical",
            "account", or "other".
        urgency: The ticket's urgency level: "low", "medium", or "high".
        ticket_id: A unique identifier for the ticket being routed (e.g.
            one you assign on the client side, like "t-001").
    """
    entry = {
        "ticket_id": ticket_id,
        "category": category,
        "urgency": urgency,
        "queue": f"{category}-{urgency}",
        "routed_at": datetime.now(timezone.utc).isoformat(),
    }

    with QUEUE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return {
        "status": "routed",
        "queue": entry["queue"],
        "ticket_id": ticket_id,
    }


if __name__ == "__main__":
    # No argument needed -- stdio is the default transport, and it's the
    # standard choice for a server your client spawns locally as a
    # subprocess (vs. streamable-http/SSE for a server running elsewhere).
    mcp.run()