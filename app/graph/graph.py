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


def _route_after_orchestrator(state: ContentEngineState) -> Literal["content_agent", "video_agent"]:
    # Tier 3 checkpoint — דלג ישר ל-video_agent
    if state.get("current_video_ref"):
        logger.info(
            "[%s] Graph router: video checkpoint detected — skipping to video_agent",
            state.get("task_id", "?"),
        )
        return "video_agent"
    return "content_agent"

def _route_after_content_agent(state) -> Literal["image_agent", "content_validator"]:
    pipeline = state.get("pipeline_type", "text_only")
    is_retry = state.get("retry_count", 0) > 0
    has_images = bool(state.get("generated_images"))

    if pipeline == "text_only":
        return "content_validator"
    # בretry כשכבר יש תמונות — דלג על Image Agent
    if is_retry and has_images and pipeline == "text_image":
        return "content_validator"
    return "image_agent"

def _route_after_image_agent(state: ContentEngineState) -> Literal["video_agent", "content_validator"]:
    return "video_agent" if state.get("pipeline_type") == "full_video" else "content_validator"

def _route_after_validator(state: ContentEngineState) -> Literal["content_agent", "__end__"]:
    from app.config import get_settings
    status      = state.get("status", "completed")
    retry_count = state.get("retry_count", 0)
    max_retries = get_settings().max_retries_per_item

    # FIX: was `retry_count <= max_retries` → infinite loop when retry_count == max_retries.
    # Correct condition: strictly less than, so we stop when exhausted.
    if status == "processing" and retry_count < max_retries:
        logger.info(
            "[%s] Graph router: retry %d/%d → content_agent",
            state.get("task_id", "?"), retry_count, max_retries,
        )
        return "content_agent"

    logger.info(
        "[%s] Graph router: → END (status=%s retry_count=%d)",
        state.get("task_id", "?"), status, retry_count,
    )
    return END


def build_graph() -> tuple[StateGraph, MemorySaver]:
    builder = StateGraph(ContentEngineState)

    builder.add_node("orchestrator",      _orchestrator_node)
    builder.add_node("content_agent",     _content_agent_node)
    builder.add_node("image_agent",       _image_agent_node)
    builder.add_node("video_agent",       _video_agent_node)
    builder.add_node("content_validator", _content_validator_node)

    builder.set_entry_point("orchestrator")
    builder.add_conditional_edges(
        "orchestrator",
        _route_after_orchestrator,
        {"content_agent": "content_agent", "video_agent": "video_agent"}
    )
    builder.add_conditional_edges("content_agent",     _route_after_content_agent, {"image_agent": "image_agent", "content_validator": "content_validator"})
    builder.add_conditional_edges("image_agent",       _route_after_image_agent,  {"video_agent": "video_agent",  "content_validator": "content_validator"})
    builder.add_edge("video_agent", "content_validator")
    builder.add_conditional_edges("content_validator", _route_after_validator,    {"content_agent": "content_agent", END: END})

    checkpointer = MemorySaver()
    compiled     = builder.compile(checkpointer=checkpointer)
    logger.info("LangGraph compiled: nodes=%s", list(builder.nodes.keys()))
    return compiled, checkpointer


_graph = _checkpointer = None

def get_graph():
    global _graph, _checkpointer
    if _graph is None:
        _graph, _checkpointer = build_graph()
    return _graph

def get_checkpointer():
    get_graph()
    return _checkpointer