from __future__ import annotations
import json
import logging
import re
from typing import Any

from app.config import get_settings
from app.graph.state import ContentEngineState
from app.services.claude_client import complete, estimate_cost
from app.services.s3_client import upload_json, asset_key

logger = logging.getLogger(__name__)

PERSONAS = [
    ("food_blogger",         "enthusiastic food blogger who documents every meal"),
    ("home_cook",            "passionate home cook always looking for new recipes"),
    ("nutrition_enthusiast", "health-conscious person focused on balanced eating"),
    ("skeptical_commenter",  "slightly skeptical but curious person"),
    ("cooking_beginner",     "complete beginner just learning to cook"),
    ("professional_chef",    "experienced chef with high standards"),
    ("busy_parent",          "time-strapped parent feeding a family"),
    ("student_budget",       "student cooking on a tight budget"),
    ("food_photographer",    "food photographer obsessed with presentation"),
    ("diet_conscious",       "diet-conscious person watching their macros"),
]

ENTHUSIASM_LEVELS = [
    "very excited", "casually positive", "mildly curious",
    "warmly supportive", "humorously enthusiastic",
]

CAPTION_LIMITS = {
    "instagram": 2200, "tiktok": 2200, "twitter": 280,
    "telegram": 4096, "facebook": 63206,
}

HASHTAG_LIMITS = {
    "instagram": 30, "tiktok": 30, "twitter": 5,
    "telegram": 0, "facebook": 10,
}


def _build_comments_prompt(state: ContentEngineState) -> str:
    quantity = state["quantity"]
    lang = state["language"]
    desc = state["description"]

    persona_assignments = []
    for idx in range(quantity):
        persona_name, persona_desc = PERSONAS[idx % len(PERSONAS)]
        enthusiasm = ENTHUSIASM_LEVELS[idx % len(ENTHUSIASM_LEVELS)]
        persona_assignments.append(
            f"  Comment {idx + 1}: persona={persona_name} ({persona_desc}), tone={enthusiasm}"
        )
    persona_block = "\n".join(persona_assignments)
    lang_instruction = (
        "Write all comments in Hebrew (rtl, natural colloquial Hebrew)."
        if lang == "he" else "Write all comments in English."
    )

    return f"""Generate exactly {quantity} unique social media comments about: "{desc}"

{lang_instruction}

Persona assignments:
{persona_block}

Rules:
- Each comment must sound authentically human, NOT AI-generated
- Each comment must be distinct — no duplicate phrasing
- Length: 1-3 sentences per comment
- No hashtags in comments
- Match the persona's voice and the specified tone

Return ONLY a valid JSON array with {quantity} objects. No preamble, no markdown fences.
Schema per object: {{"index": 0, "text": "...", "persona": "food_blogger"}}"""


def _build_captions_prompt(state: ContentEngineState) -> str:
    quantity = state["quantity"]
    lang = state["language"]
    desc = state["description"]
    platform = state["platform"]
    char_limit = CAPTION_LIMITS.get(platform, 2200)
    hashtag_limit = HASHTAG_LIMITS.get(platform, 20)
    lang_instruction = (
        "Write all captions in Hebrew." if lang == "he"
        else "Write all captions in English."
    )

    angles = [
        "restaurant ambiance and atmosphere",
        "close-up of the dish and ingredients",
        "the overall dining experience and mood",
        "behind-the-scenes / preparation story",
        "personal connection / why this meal matters",
    ]
    angle_block = "\n".join(
        f"  Caption {i + 1}: angle={angles[i % len(angles)]}" for i in range(quantity)
    )

    return f"""Generate exactly {quantity} unique {platform} post captions about: "{desc}"

{lang_instruction}

Angle assignments:
{angle_block}

Rules:
- Max {char_limit} characters per caption
- Include {hashtag_limit} relevant hashtags per caption (inline at end)
- Tone: authentic, engaging, platform-appropriate for {platform}
- Each caption must have a distinct angle as assigned

Return ONLY a valid JSON array with {quantity} objects. No preamble, no markdown fences.
Schema: {{"index": 0, "text": "...", "hashtags": ["#tag1", "#tag2"], "angle": "..."}}"""


def _build_reels_script_prompt(state: ContentEngineState) -> str:
    lang = state["language"]
    desc = state["description"]
    lang_instruction = (
        "Write the script and ALL caption text in Hebrew." if lang == "he"
        else "Write the script and all captions in English."
    )
    caption_note = (
        "Caption text will be rendered in Hebrew directly onto video frames. Keep each caption concise (max 8 Hebrew words)."
        if lang == "he"
        else "Caption text will be embedded directly into video frames by Veo 3.1, so keep each caption concise (max 8 words)."
    )

    return f"""Generate a 30-second video Reel script about: "{desc}"

{lang_instruction}

Structure: exactly 4 scenes (8s + 7s + 7s + 7s = 29 seconds total)

{caption_note}

Scene requirements:
1. Scene 1 (8s): Opening hook — ingredient prep / raw ingredients close-up
2. Scene 2 (7s): Cooking in action — heat, steam, sizzle
3. Scene 3 (7s): Plating and presentation
4. Scene 4 (7s): Final beauty shot / call to action

Return ONLY a valid JSON object. No preamble, no markdown fences.
Schema:
{{
  "index": 0,
  "scenes": [
    {{"scene": 1, "duration_sec": 8, "visual_description": "...", "caption_text": "...", "audio_mood": "..."}},
    {{"scene": 2, "duration_sec": 7, "visual_description": "...", "caption_text": "...", "audio_mood": "..."}},
    {{"scene": 3, "duration_sec": 7, "visual_description": "...", "caption_text": "...", "audio_mood": "..."}},
    {{"scene": 4, "duration_sec": 7, "visual_description": "...", "caption_text": "...", "audio_mood": "..."}}
  ],
  "hashtags": ["#tag1", "#tag2"],
  "full_caption": "..."
}}"""


def _extract_json(text: str) -> Any:
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    return json.loads(cleaned)


async def run(state: ContentEngineState) -> dict:
    content_type = state["content_type"]
    task_id = state["task_id"]
    item_index = state["item_index"]
    platform = state["platform"]

    logger.info("[%s] ContentAgent: item_%d type=%s", task_id, item_index, content_type)

    retry_feedback = ""
    for vr in state.get("validation_results", []):
        if vr.get("retry_feedback"):
            retry_feedback = f"\n\nPrevious attempt was rejected: {vr['retry_feedback']}. Fix these issues."

    if content_type == "comment":
        prompt = _build_comments_prompt(state) + retry_feedback
        system = "You are an expert social media copywriter. Output ONLY valid JSON."
    elif content_type == "reels":
        prompt = _build_reels_script_prompt(state) + retry_feedback
        system = "You are an expert video script writer. Output ONLY valid JSON."
    else:
        prompt = _build_captions_prompt(state) + retry_feedback
        system = "You are an expert social media copywriter. Output ONLY valid JSON."

    response = await complete(
        messages=[{"role": "user", "content": prompt}],
        system=system,
        max_tokens=8192,
    )

    cost = estimate_cost(response)
    raw_text = response.content[0].text

    try:
        parsed = _extract_json(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("[%s] ContentAgent JSON parse error: %s\nRaw: %s", task_id, exc, raw_text[:500])
        raise

    if isinstance(parsed, dict):
        parsed = [parsed]

    s3_key = asset_key(task_id, platform, content_type, item_index, "content.json")
    await upload_json(s3_key, parsed)

    logger.info("[%s] ContentAgent: item_%d generated %d item(s) cost=$%.4f", task_id, item_index, len(parsed), cost)

    return {
        "generated_texts": parsed,
        "cost_accumulated": state.get("cost_accumulated", 0.0) + cost,
    }