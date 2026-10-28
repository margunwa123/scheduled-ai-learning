"""
Minimal ReAct agent, built once at cold start and reused across warm invocations.

This is deliberately a throwaway example: a calculator tool (real) and a stub
"stock lookup" tool (fake data, clearly labeled) just to exercise the deploy
mechanics end to end. Section 7 replaces this module's tools and model prompt
with the real IDX multi-agent graph -- main.py's FastAPI wiring doesn't need
to change.

create_react_agent is LangGraph's prebuilt constructor for exactly the graph
shape we covered conceptually: a call_model node, a conditional edge that
checks tool_calls presence/absence on the last message, a tool-execution node
that supports parallel calls, and a loop back to call_model. Worth inspecting
its source once (it's small) to see that mapping directly; for the milestone's
custom critic<->helper nested loop we'll build the graph by hand instead,
since that control flow isn't something the prebuilt covers.
"""

import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent


def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression, e.g. '12.5 * 3 + 1'."""
    allowed = set("0123456789.+-*/() ")
    if not set(expression) <= allowed:
        return f"Rejected: '{expression}' contains characters outside basic arithmetic."
    try:
        # Safe-ish because the character whitelist above excludes names/attrs/calls.
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as exc:  # noqa: BLE001 - deliberately broad for a toy tool
        return f"Could not evaluate '{expression}': {exc}"


def get_stock_price(ticker: str) -> str:
    """STUB TOOL -- returns fake placeholder data, not real market data.

    Section 7 replaces this with a real IDX data call (ownership / disclosure
    lookups). Kept here only so the agent has a second tool to demonstrate
    tool selection and parallel tool calls.
    """
    fake_prices = {"BBCA": 9875, "BBRI": 4320, "TLKM": 2980, "ASII": 5150}
    price = fake_prices.get(ticker.upper())
    if price is None:
        return f"No stub data for '{ticker}'. Known stub tickers: {list(fake_prices)}."
    return f"[STUB DATA] {ticker.upper()}: IDR {price} (placeholder, not real)"


def build_agent():
    model = ChatGoogleGenerativeAI(
        model=os.environ.get("AGENT_MODEL", "gemini-3.8-flash"),
        google_api_key=os.environ["GEMINI_API_KEY"],
    )
    tools = [calculator, get_stock_price]
    return create_react_agent(model, tools)


# Built once per cold start, reused across every warm invocation of the
# same Lambda execution environment -- this is the "don't rebuild the graph
# per request" piece that matters once you're paying per invocation.
_agent = build_agent()


def run_agent(query: str) -> str:
    result = _agent.invoke({"messages": [{"role": "user", "content": query}]})
    return result["messages"][-1].text
