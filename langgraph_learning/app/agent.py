import json
import os
import re
from typing import Annotated, Literal, Optional, TypedDict
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START
from langgraph.graph.message import StateGraph, add_messages
from langgraph.checkpoint.memory import MemorySaver

from dotenv import load_dotenv
from langgraph.prebuilt import ToolNode

from .tools import (
    delete_source_tool,
    get_company_filings,
    list_sources_tool,
    search_filings,
)

load_dotenv()

TOOLS = [search_filings, get_company_filings, list_sources_tool, delete_source_tool]

HELPER_MODEL = os.environ.get("HELPER_MODEL", "gemini-3.8-flash")
CRITIC_MODEL = os.environ.get("CRITIC_MODEL", "gemini-3.8-flash")

MAX_CRITIC_RETRIES = 2

# Set AGENT_TRACE=0 to silence this -- on by default for the CLI, but this
# is the same agent.py that'll eventually sit behind FastAPI on Cloud Run,
# where you don't want every request dumping internals to prod logs.
TRACE = os.environ.get("AGENT_TRACE", "1") == "1"


def _trace(label: str, msg: str) -> None:
    if TRACE:
        print(f"[{label}] {msg}")


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    critic_verdict: Optional[Literal["approve", "reject"]]
    critic_reasoning: Optional[str]
    critic_retries: int


def _extract_text(content) -> str:
    # AIMessage.content is str | list[str | dict] -- some providers (Gemini
    # among them, via langchain_google_genai) return content as a list of
    # parts like {"type": "text", "text": "..."} instead of a flat string.
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
        return "".join(parts)
    return str(content)


HELPER_SYSTEM_PROMPT = """You are an IDX (Indonesia Stock Exchange) disclosure research \
assistant. Use the available tools to find real evidence before answering — never \
answer from memory. Every claim in your final answer must trace back to a specific \
chunk a tool returned; cite the doc_id and chunk_index for each claim. If the tools \
turn up no relevant evidence for the question, say so plainly instead of guessing. \
If a critic rejects your draft, address the specific concern it raises rather than \
rewording the same answer."""

_helper_llm = ChatGoogleGenerativeAI(model=HELPER_MODEL).bind_tools(TOOLS)


def helper_node(state: State) -> dict:
    # The system prompt is prepended on every call, never stored in
    # state["messages"] — storing it there would re-append a duplicate each
    # time add_messages merges this node's return value into the list.
    response = _helper_llm.invoke(
        [SystemMessage(HELPER_SYSTEM_PROMPT)] + state["messages"]
    )

    if TRACE:
        calls = getattr(response, "tool_calls", None)
        if calls:
            for c in calls:
                _trace("helper", f"-> tool call: {c['name']}({c['args']})")
        else:
            preview = _extract_text(response.content)[:200]
            _trace("helper", f"-> draft answer, no more tool calls: {preview!r}...")

    return {"messages": [response]}


def helper_router(state: State) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        _trace("helper_router", "tool_calls present -> tools")
        return "tools"
    _trace("helper_router", "no tool_calls -> critic")
    return "critic"


# ---------------------------------------------------------------------------
# tools node
# ---------------------------------------------------------------------------

_tool_node = ToolNode(TOOLS)

# search_filings returns list[dict], which the @tool wrapper stringifies into
# ToolMessage.content as a Python repr -- and the dict's own key order is
# ["doc_id", "company", "sector", "classification", "summary", "chunk_index",
# "chunk_text", "distance"]. "summary" is a full LLM-written paragraph that's
# IDENTICAL for every chunk of a given doc_id, and it sits right before
# chunk_index in that repr -- so a short preview can easily get eaten
# entirely by `summary` before ever reaching chunk_index, making every
# result look like a verbatim duplicate even when the chunks differ. Pull
# chunk_index out with a regex instead of relying on where the preview
# happens to get cut off, so we can tell "stuck on the same chunks" apart
# from "different chunks, misleading preview" regardless of summary length.
_CHUNK_INDEX_RE = re.compile(r"'chunk_index':\s*(\d+)")


def tools_node(state: State) -> dict:
    # Thin wrapper around the prebuilt ToolNode, just to print what's going
    # in and out -- ToolNode itself has no trace hook, so this prints before
    # and after delegating to its real logic rather than reimplementing it.
    last = state["messages"][-1]
    for call in getattr(last, "tool_calls", []) or []:
        _trace("tools", f"calling {call['name']}({call['args']})")

    result = _tool_node.invoke(state)

    for msg in result.get("messages", []):
        text = _extract_text(msg.content)
        preview = text[:300]
        suffix = "..." if len(text) > 300 else ""
        chunk_indexes = _CHUNK_INDEX_RE.findall(text)
        line = f"-> result: {preview!r}{suffix}"
        if chunk_indexes:
            # The bit that actually answers "is this looping on the same
            # evidence" -- compare this list across consecutive calls.
            line += f" | chunk_index(es): {chunk_indexes}"
        _trace("tools", line)

    return result


# ---------------------------------------------------------------------------
# critic node
# ---------------------------------------------------------------------------

CRITIC_SYSTEM_PROMPT = """You are a fact-checking critic. You will be shown a user's \
question, the raw evidence tools returned, and a draft answer. You do not see how the \
draft was produced — only judge whether every factual claim in it is actually \
supported by the evidence shown. Respond with JSON only, no markdown fences, matching \
exactly this shape: {"verdict": "approve" or "reject", "reasoning": "<one or two \
sentences, specific enough for the writer to act on>"}."""

_critic_llm = ChatGoogleGenerativeAI(model=CRITIC_MODEL)


def _build_critic_prompt(messages: list[AnyMessage]) -> str:
    # The *latest* real user question, not the first one in the thread --
    # search in reverse, and skip past append_critic_feedback's own
    # HumanMessage (tagged name="critic_feedback") so a mid-turn retry
    # doesn't accidentally grab the critic's own feedback as "the question."
    query = next(
        m.content
        for m in reversed(messages)
        if isinstance(m, HumanMessage) and m.name != "critic_feedback"
    )
    # Evidence deliberately still scans the whole thread, not just this
    # turn -- confirmed useful, not just a leftover bug: it's what let the
    # critic correctly explain "...after the deletion of X" on a later turn
    # using an earlier turn's tool result. Kept as a tradeoff (grows with
    # session length) rather than "fixed" to scope-per-turn.
    evidence = "\n\n".join(
        f"[tool result] {m.content}" for m in messages if isinstance(m, ToolMessage)
    )
    draft = messages[
        -1
    ].content  # helper_router only sends us here when this has no tool_calls
    return f"""Question:
{query}

Evidence returned by tools:
{evidence or "(no tool results — check whether the draft fabricated anything)"}

Draft answer to check:
{draft}"""


def critic_node(state: State) -> dict:
    prompt = _build_critic_prompt(state["messages"])
    response = _critic_llm.invoke(
        [SystemMessage(CRITIC_SYSTEM_PROMPT), HumanMessage(prompt)]
    )
    reasoning = ""
    retries = state.get("critic_retries", 0)

    try:
        parsed = json.loads(_extract_text(response.content))
        verdict = parsed["verdict"]
        reasoning = parsed["reasoning"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        reasoning = f"Critic response couldn't be parsed ({e}); treating as unverified."
        verdict = "reject"

    if verdict == "reject":
        retries += 1

    _trace("critic", f"verdict={verdict} retries={retries} reasoning={reasoning!r}")

    return {
        "critic_verdict": verdict,
        "critic_reasoning": reasoning,
        "critic_retries": retries,
    }


def critic_router(state: State) -> str:
    if state["critic_verdict"] == "approve":
        _trace("critic_router", "approve -> action")
        return "approve"
    if state["critic_retries"] >= MAX_CRITIC_RETRIES:
        _trace("critic_router", f"reject, retries={state['critic_retries']} exhausted -> insufficient_data")
        return "insufficient"
    _trace("critic_router", f"reject, retries={state['critic_retries']} left -> retry")
    return "retry"


def append_critic_feedback(state: State) -> dict:
    """Deterministic — the retry-limit check already happened in critic_router.
    This node's only job is turning the critic's reasoning into a new input
    message the helper will see on its next turn, without touching the
    rest of the message history (the helper keeps its prior tool calls and
    results — this is a continuation, not a restart)."""
    feedback = (
        f"A critic reviewed your last answer and rejected it: {state['critic_reasoning']}\n"
        "Revise your answer to address this — use more tool calls if you need more evidence."
    )
    _trace("append_critic_feedback", f"feeding back to helper: {feedback!r}")
    return {"messages": [HumanMessage(content=feedback, name="critic_feedback")]}


# ---------------------------------------------------------------------------
# terminal nodes
# ---------------------------------------------------------------------------


def action_node(state: State) -> dict:
    # Stub -- Stage 5 adds the real notability judgment + alert drafting.
    _trace("action", "approved (stub -- no notability judgment yet)")
    return {}


def insufficient_data_node(state: State) -> dict:
    content = (
        "I don't have strong enough evidence to answer this confidently. "
        f"Last concern raised: {state.get('critic_reasoning') or 'none recorded'}"
    )
    _trace("insufficient_data", "bailing out -- no LLM call here, deterministic")
    return {"messages": [AIMessage(content=content)]}


def build_graph():
    graph = StateGraph(State)

    graph.add_node("helper", helper_node)
    graph.add_node("tools", tools_node)
    graph.add_node("critic", critic_node)
    graph.add_node("append_critic_feedback", append_critic_feedback)
    graph.add_node("action", action_node)
    graph.add_node("insufficient_data", insufficient_data_node)

    graph.add_edge(START, "helper")
    graph.add_conditional_edges(
        "helper", helper_router, {"tools": "tools", "critic": "critic"}
    )
    graph.add_edge("tools", "helper")
    graph.add_conditional_edges(
        "critic",
        critic_router,
        {
            "approve": "action",
            "retry": "append_critic_feedback",
            "insufficient": "insufficient_data",
        },
    )
    graph.add_edge("append_critic_feedback", "helper")
    graph.add_edge("action", END)
    graph.add_edge("insufficient_data", END)

    return graph.compile(checkpointer=MemorySaver())


graph = build_graph()