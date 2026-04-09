from __future__ import annotations
import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.graph.state import ContentEngineState

logger = logging.getLogger(__name__)


async def _orchestrator_node(state: ContentEngineState) -> dict:
    from app.agents.orchestrator import run
    return await run(state)


async def _content_agent_node(state: ContentEngineState) -> dict:
    from app.agents.content_agent import run
    return await run(state)


async def _image_agent_node(state: ContentEngineState) -> dict:
    from app.agents.image_agent import run
    return await run(state)


async def _video_agent_node(state: ContentEngineState) -> dict:
    from app.agents.video_agent import run
    return await run(state)


async def _content_validator_node(state: ContentEngineState) -> dict:
    from app.agents.content_validator import run
    return await run(state)


def _route_after_orchestrator(state: ContentEngineState) -> Literal["content_agent"]:
    return "content_agent"


def _route_after_content_agent(
    state: ContentEngineState,
) -> Literal["image_agent", "content_validator"]:
    pipeline = state.get("pipeline_type", "text_only")
    if pipeline == "text_only":
        return "content_validator"
    return "image_agent"


def _route_after_image_agent(
    state: ContentEngineState,
) -> Literal["video_agent", "content_validator"]:
    pipeline = state.get("pipeline_type", "text_image")
    if pipeline == "full_video":
        return "video_agent"
    return "content_validator"


def build_graph() -> tuple[StateGraph, MemorySaver]:
    builder = StateGraph(ContentEngineState)

    builder.add_node("orchestrator", _orchestrator_node)
    builder.add_node("content_agent", _content_agent_node)
    builder.add_node("image_agent", _image_agent_node)
    builder.add_node("video_agent", _video_agent_node)
    builder.add_node("content_validator", _content_validator_node)

    builder.set_entry_point("orchestrator")

    builder.add_conditional_edges(
        "orchestrator",
        _route_after_orchestrator,
        {"content_agent": "content_agent"},
    )

    builder.add_conditional_edges(
        "content_agent",
        _route_after_content_agent,
        {
            "image_agent": "image_agent",
            "content_validator": "content_validator",
        },
    )

    builder.add_conditional_edges(
        "image_agent",
        _route_after_image_agent,
        {
            "video_agent": "video_agent",
            "content_validator": "content_validator",
        },
    )

    builder.add_edge("video_agent", "content_validator")
    builder.add_edge("content_validator", END)

    checkpointer = MemorySaver()
    compiled = builder.compile(checkpointer=checkpointer)

    logger.info("LangGraph compiled: nodes=%s", list(builder.nodes.keys()))
    return compiled, checkpointer


_graph = None
_checkpointer = None


def get_graph():
    global _graph, _checkpointer
    if _graph is None:
        _graph, _checkpointer = build_graph()
    return _graph


def get_checkpointer():
    get_graph()
    return _checkpointer