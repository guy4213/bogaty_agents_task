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

CAPTION_LIMITS  = {
    "instagram": 2200, "tiktok": 2200, "twitter": 280,
    "telegram": 4096,  "facebook": 63206,
}
HASHTAG_LIMITS  = {
    "instagram": 30, "tiktok": 30, "twitter": 5,
    "telegram": 0,   "facebook": 10,
}

# Angles list shared with mock so both pick the same angle for a given item_index
CAPTION_ANGLES = [
    "restaurant ambiance and atmosphere",
    "close-up of the dish and ingredients",
    "the overall dining experience and mood",
    "behind-the-scenes / preparation story",
    "personal connection / why this meal matters",
]


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_comments_prompt(state: ContentEngineState) -> str:
    """All N comments in one single Claude call — unchanged."""
    quantity = state["quantity"]
    lang     = state["language"]
    desc     = state["description"]

    persona_assignments = []
    for idx in range(quantity):
        persona_name, persona_desc = PERSONAS[idx % len(PERSONAS)]
        enthusiasm = ENTHUSIASM_LEVELS[idx % len(ENTHUSIASM_LEVELS)]
        persona_assignments.append(
            f"  Comment {idx + 1}: persona={persona_name} ({persona_desc}), tone={enthusiasm}"
        )
    persona_block    = "\n".join(persona_assignments)
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


def _build_single_caption_prompt(state: ContentEngineState) -> str:
    """
    FIX: generates exactly ONE caption per item, using item_index to select
    the angle. Previously the function generated `quantity` captions every
    time and image_agent always used index 0 → all posts got the same angle.

    Also: visual_style_descriptor is only requested on item 0 (it anchors
    the style for all images via the style_reference_image mechanism).
    """
    item_index    = state["item_index"]
    lang          = state["language"]
    desc          = state["description"]
    platform      = state["platform"]
    char_limit    = CAPTION_LIMITS.get(platform, 2200)
    hashtag_limit = HASHTAG_LIMITS.get(platform, 20)
    is_first_item = item_index == 0

    lang_instruction = (
        "Write the caption in Hebrew." if lang == "he"
        else "Write the caption in English."
    )
    angle = CAPTION_ANGLES[item_index % len(CAPTION_ANGLES)]

    # Only item 0 generates the visual_style_descriptor anchor.
    # Items 1+ receive it via state from the runner.
    style_section = """
Also produce a "visual_style_descriptor" — one sentence (max 25 words) that locks
the visual style for ALL images in this batch. Specify: lighting temperature,
color palette, camera angle, depth of field, and mood.
Example: "Warm candlelit tones, rich ochre palette, shallow DOF close-up, intimate romantic mood."
""" if is_first_item else ""

    return f"""Generate exactly 1 {platform} post caption about: "{desc}"

item_index: {item_index}
Angle for this caption: {angle}

{lang_instruction}

Rules:
- Max {char_limit} characters
- Include {hashtag_limit} relevant hashtags (inline at end)
- Tone: authentic, engaging, platform-appropriate for {platform}
- Angle MUST be: {angle}
{style_section}
Return ONLY a valid JSON object. No preamble, no markdown fences.
Schema:
{{
  "visual_style_descriptor": "...",
  "captions": [
    {{"index": 0, "text": "...", "hashtags": ["#tag1", "#tag2"], "angle": "{angle}"}}
  ]
}}"""


def _build_reels_script_prompt(state: ContentEngineState) -> str:
    lang = state["language"]
    desc = state["description"]
    lang_instruction = (
        "Write the script and ALL caption text in Hebrew." if lang == "he"
        else "Write the script and all captions in English."
    )
    caption_note = (
        "Caption text will be rendered onto video frames. Keep each caption concise (max 8 Hebrew words)."
        if lang == "he"
        else "Caption text will be embedded into video frames. Keep each caption concise (max 8 words)."
    )

    return f"""Generate a 30-second video Reel script about: "{desc}"

{lang_instruction}

Structure: exactly 4 scenes (8s + 7s + 7s + 7s = 29 seconds total)

{caption_note}

IMPORTANT: Veo video model cannot render RTL text correctly.
For each scene you MUST provide TWO caption fields:
- "caption_text":    the caption in {("Hebrew" if lang == "he" else "English")} (for script.txt)
- "caption_text_en": the English translation (for Veo rendering — always English)

Also produce a "visual_style_descriptor" — one sentence (max 25 words) locking the
visual style for ALL scenes and the thumbnail.

CRITICAL — scenes must follow strict chronological story progression.
The entire video tells ONE continuous story — same location, same subject, same visual language:
- Scene 1 (8s): Opening hook — establish the subject, raw/initial state
- Scene 2 (7s): Action/process — the transformation or key action happening
- Scene 3 (7s): Progress/detail — close-up of the key moment or result developing
- Scene 4 (7s): Final reveal — completed result, beauty shot, call to action

STRICTLY FORBIDDEN:
- Do NOT introduce new elements not present from the start
- Do NOT change location or setting between scenes
- Each visual_description must reference the SAME specific subject throughout

AUDIO — this is critical for viewer engagement:
For each scene's "audio_mood", be VERY specific and match it to the video content:
- Describe the exact music genre (e.g. "upbeat lo-fi hip hop", "warm acoustic guitar", "cinematic orchestral build")
- Describe the energy level (e.g. "energetic and rhythmic", "calm and warm", "building excitement")
- Include ambient sounds relevant to the scene (e.g. "sizzling sounds", "crowd ambience", "nature sounds")
- Keep musical theme CONSISTENT across all 4 scenes — same genre, evolving energy
- Match the platform: TikTok = energetic and modern, Instagram = warm and aspirational

Example for a cooking video:
"upbeat Mediterranean acoustic guitar, rhythmic and warm, with sizzling kitchen ambience sounds"

Return ONLY a valid JSON object. No preamble, no markdown fences.
Schema:
{{
  "index": 0,
  "visual_style_descriptor": "...",
  "scenes": [
    {{
      "scene": 1,
      "duration_sec": 8,
      "visual_description": "...",
      "caption_text": "...",
      "caption_text_en": "...",
      "audio_mood": "upbeat [genre], [energy], with [ambient sounds]"
    }},
    {{
      "scene": 2,
      "duration_sec": 7,
      "visual_description": "...",
      "caption_text": "...",
      "caption_text_en": "...",
      "audio_mood": "..."
    }},
    {{
      "scene": 3,
      "duration_sec": 7,
      "visual_description": "...",
      "caption_text": "...",
      "caption_text_en": "...",
      "audio_mood": "..."
    }},
    {{
      "scene": 4,
      "duration_sec": 7,
      "visual_description": "...",
      "caption_text": "...",
      "caption_text_en": "...",
      "audio_mood": "..."
    }}
  ],
  "hashtags": ["#tag1", "#tag2"],
  "full_caption": "..."
}}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Any:
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    return json.loads(cleaned)


def _extract_visual_style(parsed: Any) -> str:
    if isinstance(parsed, dict):
        return parsed.get("visual_style_descriptor", "")
    return ""


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

async def run(state: ContentEngineState) -> dict:
    content_type = state["content_type"]
    task_id      = state["task_id"]
    item_index   = state["item_index"]
    platform     = state["platform"]
    retry_count  = state.get("retry_count", 0)

    logger.info(
        "[%s] ContentAgent: item_%d type=%s retry=%d",
        task_id, item_index, content_type, retry_count,
    )

    # Pull retry feedback from validator
    retry_feedback = ""
    for vr in state.get("validation_results", []):
        if vr.get("retry_feedback"):
            retry_feedback = (
                f"\n\nPrevious attempt rejected: {vr['retry_feedback']}. Fix these issues."
            )
            break

    if content_type == "comment":
        prompt = _build_comments_prompt(state) + retry_feedback
        system = "You are an expert social media copywriter. Output ONLY valid JSON."
    elif content_type == "reels":
        prompt = _build_reels_script_prompt(state) + retry_feedback
        system = "You are an expert video script writer. Output ONLY valid JSON."
    else:
        # FIX: ONE caption per item, angle driven by item_index
        prompt = _build_single_caption_prompt(state) + retry_feedback
        system = "You are an expert social media copywriter. Output ONLY valid JSON."

    response = await complete(
        messages=[{"role": "user", "content": prompt}],
        system=system,
        max_tokens=8192,
    )

    cost     = estimate_cost(response)
    raw_text = response.content[0].text

    try:
        parsed = _extract_json(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("[%s] ContentAgent JSON parse error: %s\nRaw: %s", task_id, exc, raw_text[:500])
        raise

    visual_style_descriptor = _extract_visual_style(parsed)

    # Normalise → flat list
    if isinstance(parsed, dict):
        if content_type in ("post", "story") and "captions" in parsed:
            items = parsed["captions"]   # always length 1 after the fix
        else:
            items = [parsed]
    else:
        items = parsed  # already a list (comments)

    s3_key = asset_key(task_id, platform, content_type, item_index, "content.json")
    await upload_json(s3_key, items)

    logger.info(
        "[%s] ContentAgent: item_%d generated %d item(s) cost=$%.4f",
        task_id, item_index, len(items), cost,
    )

    updates: dict = {
        "generated_texts": items,
        "cost_accumulated": state.get("cost_accumulated", 0.0) + cost,
        # FIX: clear downstream artefacts so image/video agents start fresh on
        # every content_agent call (including retries after validation failure).
        "generated_images":  [],
        "generated_videos":  [],
        "current_video_ref": None,
        "completed_extends": 0,
    }

    # visual_style_descriptor: first item sets the anchor; subsequent items keep
    # whatever is already in state (passed in from runner via style_reference_image).
    if visual_style_descriptor and not state.get("visual_style_descriptor"):
        updates["visual_style_descriptor"] = visual_style_descriptor

    return updates