import json
import os
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
CRITIC_MODEL = os.environ.get("HELPER_MODEL", "gemini-3.8-flash")

MAX_CRITIC_RETRIES = 2


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    critic_verdict: Optional[Literal["approve", "reject"]]
    critic_reasoning: Optional[str]
    critic_retries: int


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
    return {"messages": [response]}


def helper_router(state: State) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return "critic"


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
    query = next(m.content for m in messages if isinstance(m, HumanMessage))
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


def _extract_text(content) -> str:
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
    return {
        "critic_verdict": verdict,
        "critic_reasoning": reasoning,
        "critic_retries": retries,
    }


def critic_router(state: State) -> str:
    if state["critic_verdict"] == "approve":
        return "approve"
    if state["critic_retries"] >= MAX_CRITIC_RETRIES:
        return "insufficient"
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
    return {"messages": [HumanMessage(content=feedback)]}


# ---------------------------------------------------------------------------
# terminal nodes
# ---------------------------------------------------------------------------


def action_node(state: State) -> dict:
    return {}


def insufficient_data_node(state: State) -> dict:
    content = (
        "I don't have strong enough evidence to answer this confidently. "
        f"Last concern raised: {state.get('critic_reasoning') or 'none recorded'}"
    )
    return {"messages": [AIMessage(content=content)]}


def build_graph():
    graph = StateGraph(State)

    graph.add_node("helper", helper_node)
    graph.add_node("tools", ToolNode(TOOLS))
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
