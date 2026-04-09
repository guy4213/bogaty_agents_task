from __future__ import annotations
import logging

from app.graph.state import ContentEngineState

logger = logging.getLogger(__name__)

PIPELINE_MAP = {
    "comment": "text_only",
    "post":    "text_image",
    "story":   "text_image",
    "reels":   "full_video",
}


async def run(state: ContentEngineState) -> dict:
    content_type = state["content_type"]
    pipeline_type = PIPELINE_MAP.get(content_type, "text_only")

    logger.info(
        "[%s] Orchestrator: item_%d content_type=%s pipeline=%s lang=%s platform=%s",
        state["task_id"],
        state["item_index"],
        content_type,
        pipeline_type,
        state["language"],
        state["platform"],
    )

    return {
        "pipeline_type": pipeline_type,
        "status": "processing",
    }