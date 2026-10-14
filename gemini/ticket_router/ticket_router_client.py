"""
MCP client + Gemini bridge for the Support Ticket Router milestone project
(Phase 3, Section 5).

This is the piece that actually exercises Section 4's decide/execute split
in real code: YOU (this client) do discovery and execution; the model
only ever decides. If you keep that rule straight while filling in the
TODOs below, the architecture takes care of itself.

Open research task (this is deliberate, not an oversight): your
gemini/section_1.py code uses `client.interactions.create`, not the
classic `generate_content`. We only confirmed the classic API's
tool-declaration shape (`functionDeclarations`) back in Section 2 -- you'll
need to check what shape `interactions.create` actually wants for tools,
and write the translation in `mcp_tools_to_gemini_tools` below. Treat this
the same way you treated the generation_config surprise in Section 1:
check the real docs / experiment against the real API, don't assume.

Setup (current mcp package, 2.x line, as of Oct 2026):
    pip install "mcp[cli]"
    pip install google-genai   # or whatever package gemini/section_1.py uses

Note the API surface below is the CURRENT one, not the ClientSession /
stdio_client pattern you may see in older MCP tutorials or examples --
the SDK's 2.x line replaced that with a single `Client` class used as an
async context manager, which spawns the server and connects in one step
(no separate .initialize() call).
"""

import asyncio
import json

from mcp import Client, StdioServerParameters, Tool

from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client()

SERVER_SCRIPT = "gemini/ticket_router/ticket_router_server.py"

EXTRACTION_SYSTEM_INSTRUCTION = """
You classify incoming support tickets. For each ticket, output JSON with:
  category: one of "billing" | "technical" | "account" | "other"
  urgency: one of "low" | "medium" | "high"
  summary: a one-sentence summary
  justification: your step-by-step reasoning for the urgency level
  needs_human_review: boolean, true if you are not confident

Do not wrap the JSON in a markdown code fence.

If, and only if, the ticket is clear enough to act on, you may also call
the route_ticket tool with the category, urgency, and a ticket_id you are
given.
""".strip()

# TODO: add 2-3 more sample tickets -- include at least one deliberately
# ambiguous one (should trip needs_human_review) and consider a
# near-duplicate pair to mirror your Section 4 search_tickets scenario.
SAMPLE_TICKETS = [
    ("t-001", "My internet has been down since this morning, nobody's responded."),
    ("t-002", "Can I get a copy of my invoice from last month?"),
    ("t-003", "Hi, I want to ask what's your refund policy?"),
    ("t-004", "What's the pricnig tier?"),
    ("t-005", "Is this mcdonalds?"),
    ("t-006", "???"),
]


async def discover_tools(client: Client) -> list[Tool]:
    """
    This is the literal 'discovery' step from Section 4 -- don't hardcode
    the route_ticket schema here by hand. Fetch it from the server for
    real, the same way a client would for any MCP server it has never
    seen before.
    """
    result = await client.list_tools()

    return result.tools


def mcp_tools_to_gemini_tools(mcp_tool_list: list[Tool]):
    """
    TODO: translate the MCP tool list (each with a name, a description,
    and an inputSchema) into whatever shape your Gemini
    `client.interactions.create` call expects for tools. This is the
    open research task flagged above.
    """
    return [
        {
            "name": tool.name,
            "type": "function",
            "description": tool.description,
            "parameters": tool.input_schema,  # turns out input schema is the same as params
        }
        for tool in mcp_tool_list
    ]


MAX_RETRIES = 2


def _extract_json_from_steps(steps) -> dict | None:
    """Pull the classification JSON out of the model's text output.
    Independent of whether a function_call also happened -- the
    system_instruction asks for this JSON unconditionally, on every
    ticket, whether or not routing follows.
    """
    text_parts = []
    for step in steps:
        if getattr(step, "type", None) == "model_output":
            for block in step.content:
                if getattr(block, "type", None) == "text":
                    text_parts.append(block.text)
        if getattr(step, "type", None) == "function_call":
            return getattr(step, "arguments", None)
    raw = "".join(text_parts).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[-1] if "\n" in raw else raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


async def handle_ticket(
    genai_client: genai.Client,
    mcp_client: Client,
    gemini_tools,
    ticket_id: str,
    ticket_text: str,
) -> dict:
    last_error = None

    for attempt in range(1, MAX_RETRIES + 2):  # 1 initial try + MAX_RETRIES retries
        try:
            # Confirmed shape (Gemini docs): tools is a list of
            # {"type": "function", "name", "description", "parameters"} dicts --
            # this is what mcp_tools_to_gemini_tools should be producing.
            interaction = genai_client.interactions.create(
                model="gemini-3.8-flash",
                system_instruction=EXTRACTION_SYSTEM_INSTRUCTION,
                generation_config={
                    "max_output_tokens": 1000,
                    "thinking_level": "low",
                },
                tools=gemini_tools,
                stream=False,
                input=json.dumps({"ticket_id": ticket_id, "ticket_text": ticket_text}),
            )

            extraction = _extract_json_from_steps(interaction.steps)
            if extraction is None:
                raise ValueError(
                    f"couldn't parse classification JSON (attempt {attempt}) Steps : {interaction.steps}"
                )

            # Confirmed shape: find the function_call step, if the model made one.
            function_calls = (
                s
                for s in interaction.steps
                if getattr(s, "type", None) == "function_call"
            )
            fc_step = next(
                function_calls,
                None,
            )

            routing_outcome = {
                "routed": False,
                "reason": "model did not request routing",
            }

            if fc_step is not None and fc_step.name == "route_ticket":
                # EXECUTION happens here, client-side -- never inside the model.
                tool_result = await mcp_client.call_tool(
                    "route_ticket", fc_step.arguments
                )

                # Confirmed shape: send the result back via function_result,
                # linked by previous_interaction_id, to get the model's final word.
                final_interaction = genai_client.interactions.create(
                    model="gemini-3.8-flash",
                    input=[
                        {
                            "type": "function_result",
                            "name": fc_step.name,
                            "call_id": fc_step.id,
                            "result": [
                                {
                                    "type": "text",
                                    "text": json.dumps(tool_result.structured_content),
                                }
                            ],
                        }
                    ],
                    tools=gemini_tools,
                    previous_interaction_id=interaction.id,
                )

                routing_outcome = {
                    "routed": True,
                    "result": tool_result.structured_content,
                    "model_confirmation": final_interaction.output_text,
                }

            return {
                "ticket_id": ticket_id,
                "extraction": extraction,
                "routing": routing_outcome,
            }
        except Exception as exc:  # TODO: narrow this once you see what actually fails
            last_error = exc
            continue  # treated as retriable for now

    return {
        "ticket_id": ticket_id,
        "extraction": None,
        "routing": {"routed": False, "reason": "max retries exceeded"},
        "error": f"Could not process this ticket after {MAX_RETRIES + 1} attempts: {last_error}",
    }


async def main():
    genai_client = genai.Client()
    server_params = StdioServerParameters(command="python3", args=[SERVER_SCRIPT])

    async with Client(server_params) as mcp_client:
        mcp_tools = await discover_tools(mcp_client)
        gemini_tools = mcp_tools_to_gemini_tools(mcp_tools)

        for ticket_id, ticket_text in SAMPLE_TICKETS:
            result = await handle_ticket(
                genai_client, mcp_client, gemini_tools, ticket_id, ticket_text
            )
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
