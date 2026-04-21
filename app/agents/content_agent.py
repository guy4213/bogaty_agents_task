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



NARRATIVE_FRAMEWORKS = [
    "The Hook & Overview: Focus on the grand result, the main value, or the big picture.",
    "The Details: Focus on a specific interesting component, feature, or behind-the-scenes element.",
    "The Journey: Focus on the process, the effort, or how it came to be.",
    "The Personal Connection: Focus on why this matters, the emotional impact, or a relatable thought.",
    "The Takeaway: Focus on actionable advice, a summary thought, or an engaging question for the audience."
]
ENTHUSIASM_LEVELS = [
    "very excited", "casually positive", "mildly curious",
    "warmly supportive", "humorously enthusiastic",
]

from app.constants import CAPTION_LIMITS, HASHTAG_LIMITS


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_comments_retry_prompt(state: ContentEngineState, failed_items: list[dict]) -> str:
    lang        = state["language"]
    desc        = state["description"]
    platform    = state["platform"]
    failed_indices = [item.get("item_id") for item in failed_items]
    failed_count   = len(failed_indices)

    lang_instruction = (
        "Write ALL comments in Hebrew. Natural, conversational Israeli Hebrew only."
        if lang == "he"
        else "Write ALL comments in English. Natural, conversational language only."
    )

    feedback_items = []
    for item in failed_items:
        idx   = item.get("item_id")
        score = item.get("score", 0)
        errors = item.get("errors", [])
        if errors:
            feedback_items.append(f"  - index {idx}: score={score}, issues={errors}")

    feedback_str = "\n".join(feedback_items) if feedback_items else "  - Score too low, sounded unnatural or AI-generated"
    indices_str = ", ".join(map(str, failed_indices))

    return f"""You previously generated comments about: "{desc}"

The following {failed_count} comments (indices: {indices_str}) FAILED quality validation and must be regenerated.

Failure reasons:
{feedback_str}

{lang_instruction}

REGENERATE ONLY these {failed_count} comments. Use the SAME index numbers as above.
Rules:
- INVENT PERSONAS: For each comment, invent a NEW, highly specific and relevant persona based on the topic.
- Sound like a real person wrote it spontaneously.
- Match the persona naturally (not robotically).
- Be relevant to: "{desc}".
- Be unique — different from all other comments in the batch.
- NOT sound AI-generated or overly enthusiastic.

Platform: {platform}

Return ONLY a valid JSON array with exactly {failed_count} items. No preamble, no markdown.
Schema:
[
  {{"index": <original_index>, "text": "...", "persona": "<invented_persona_name>"}},
  ...
]"""
def _build_comments_prompt(state: ContentEngineState) -> str:
    quantity = state["quantity"]
    lang     = state["language"]
    desc     = state["description"]

    lang_instruction = (
        "Write all comments in Hebrew (rtl, natural colloquial Hebrew)."
        if lang == "he" else "Write all comments in English."
    )

    return f"""Generate exactly {quantity} unique social media comments about: "{desc}"

{lang_instruction}

Rules:
- INVENT PERSONAS: For each comment, invent a highly specific and relevant persona based on the topic. 
  (e.g., if the topic is Real Estate, personas could be 'first-time buyer' or 'investor'. If Travel, 'budget backpacker' or 'luxury traveler').
- Each comment must sound authentically human, NOT AI-generated.
- Each comment must be distinct — no duplicate phrasing or repeated personas.
- Length: 1-3 sentences per comment.
- No hashtags in comments.
- Match the invented persona's voice and tone perfectly to the comment text.

Return ONLY a valid JSON array with {quantity} objects. No preamble, no markdown fences.
Schema per object: {{"index": 0, "text": "...", "persona": "invented_persona_name"}}"""


def _build_single_caption_prompt(state: ContentEngineState) -> str:
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
    
    # שליפת השלד הסיפורי הכללי שישתנה מפוסט לפוסט
    framework = NARRATIVE_FRAMEWORKS[item_index % len(NARRATIVE_FRAMEWORKS)]

    style_section = """
Also produce a "visual_style_descriptor" — one sentence (max 25 words) that locks
the visual style for ALL images in this batch. Specify: lighting temperature,
color palette, camera angle, depth of field, and mood.

Also produce a "content_category" in 1-2 words. 
CRITICAL RULE: If the content is related to food, cooking, baking, a recipe, or any culinary topic, you MUST output exactly the word 'food'. 
For any other topic, output the specific descriptive category (e.g., 'fitness', 'real estate', 'technology', 'science').
""" if is_first_item else ""

    if is_first_item:
        schema = f"""\
{{
  "visual_style_descriptor": "...",
  "content_category": "...",
  "captions": [
    {{"index": {item_index}, "text": "...", "hashtags": ["#tag1", "#tag2"], "angle": "{framework}"}}
  ]
}}"""
    else:
        schema = f"""\
{{
  "captions": [
    {{"index": {item_index}, "text": "...", "hashtags": ["#tag1", "#tag2"], "angle": "{framework}"}}
  ]
}}"""

    return f"""Generate exactly 1 {platform} post caption about: "{desc}"

item_index: {item_index}

{lang_instruction}

Rules:
- Narrative Angle: Adapt this generic framework to the specific topic: "{framework}"
- Max {char_limit} characters
- Include {hashtag_limit} relevant hashtags (inline at end)
- Tone: authentic, engaging, platform-appropriate for {platform}
- CRITICAL: The "text" value MUST be a complete, grammatically finished thought. Never end mid-sentence or mid-word.
{style_section}
Return ONLY a valid JSON object. No preamble, no markdown fences.
Schema:
{schema}"""
def _build_reels_script_prompt(state: ContentEngineState) -> str:
    lang = state["language"]
    desc = state["description"]

    lang_instruction = (
        "Write ALL text fields (caption_text, full_caption, hashtags) in Hebrew."
        if lang == "he"
        else "Write ALL text fields in English."
    )
    caption_note = (
        "Each caption_text must be max 8 Hebrew words — short and punchy."
        if lang == "he"
        else "Each caption_text must be max 8 words — short and punchy."
    )

    return f"""You are a strict, precise AI video architecture scriptwriter. Generate a 29-second vertical Reel script.

TOPIC: "{desc}"
{lang_instruction}

════════════════════════════════════════
STEP 1 — IDENTIFY THE CANONICAL SUBJECT
════════════════════════════════════════
Define the single specific subject of this video.

Rules:
- Be hyper-specific. Name the exact object, food, person, or item.
- This exact string MUST appear at the start of EVERY scene's visual_description.
- ✅ GOOD (food): "thin spaghetti pasta with cherry tomatoes and garlic"
- ✅ GOOD (travel): "sunset view from Santorini cliffside at golden hour"
- ✅ GOOD (tech): "matte black mechanical keyboard with RGB lighting"
- ❌ BAD: "pasta" / "food" / "the subject" / "the item"

════════════════════════════════════════
STEP 2 — DEFINE THE VISUAL STYLE
════════════════════════════════════════
Define a "visual_style_descriptor" — one sentence (max 25 words) locking:
  lighting temperature, color palette, camera style, depth of field, and mood.

Examples by category — pick the style that fits your topic:
- (Food/Lifestyle): "Warm candlelit tones, rich ochre palette, shallow DOF close-ups, intimate mood."
- (Real Estate): "Bright natural light, warm whites, wide-angle airy composition, aspirational mood."
- (Travel): "Vibrant saturated colors, golden hour warmth, sweeping cinematic movement, adventurous mood."
- (Fitness): "High contrast dramatic shadows, cool steel tones, dynamic motion energy, powerful mood."
- (Technology): "Clean studio whites with accent RGB glow, macro precision close-ups, sleek modern mood."
- (News/Events): "Neutral balanced daylight, clean editorial framing, authoritative and clear mood."

Every scene's visual_description MUST weave these exact photometric properties naturally.
Same lighting, same palette, same texture and mood throughout all 4 scenes.
════════════════════════════════════════
STEP 3 — CATEGORIZE THE CONTENT
════════════════════════════════════════
Analyze the content and define its category in 1-2 words. 
CRITICAL RULE: If the content is related to food, cooking, baking, a recipe, or any culinary topic, you MUST output exactly the word 'food'. 
For any other topic, output the specific descriptive category (e.g., 'fitness', 'real estate', 'technology', 'science').
════════════════════════════════════════
════════════════════════════════════════
STEP 4 — THE NARRATIVE ARC (4 SCENES: 8s+7s+7s+7s)
════════════════════════════════════════
Structure is NON-CHRONOLOGICAL. Scene 1 is the HOOK. Scenes 2-4 run chronologically.
This applies to ANY topic (Food, Travel, Sports, Real Estate, Tech, etc.).

- Scene 1 (8s): THE HOOK / THE VISION — Show the ultimate payoff, peak moment, or final destination to grab attention.
  (Travel: stunning view of the final destination. Food: finished plated dish. Real Estate: glowing exterior).

- Scene 2 (7s): THE FOUNDATION / THE START — The starting point before the main action or journey begins.
  Show the initial components or situation clearly.
  (Travel: packing a suitcase, passports, or arriving at the airport. Food: raw ingredients spread out. Tech: unboxing).

- Scene 3 (7s): THE PROGRESSION / THE ACTION — The core journey, transformation, or active process.
  The viewer needs to see the transition from start to finish.
  CRITICAL TIMING RULE:
  - Seconds 0-2: action begins — introducing key elements (departing, pouring, entering).
  - Seconds 2-4: active progression — combining, building, traveling, exploring.
  - Seconds 4-7: action decelerates. Subject settles. End on a nearly still frame.
  This full arc (initiate → peak action → settle) is non-negotiable.
  (Travel: moving between locations → exploring → arriving at the hotel room. 
   Food: combine in pan → cook → settle still. 
   Real Estate: enter room → pan across → settle on hero spot).

- Scene 4 (7s): THE FINAL DESTINATION / THE PAYOFF — The subject is fully complete and presented in its final ideal environment.
  Camera slowly pushes in for a hero presentation.
  (Travel: relaxing at the final scenic spot. Food: plated dish beauty shot. Tech: completed device glowing).

For EACH scene provide:

1. visual_description:
   - MUST start with the canonical_subject verbatim
   - Describe EXACTLY what is physically happening in the frame
   - Weave in lighting, palette and mood from visual_style_descriptor naturally
   - Describe camera as a FLUID continuous motion
     ✅ GOOD: "camera slowly pushes in from wide to close-up"
     ❌ BAD: "close-up shot" with no transition described
   - 🚫 ZERO HALLUCINATION RULE: describe ONLY physical visible items.
     Do NOT describe sounds, music, smells, or abstract concepts.

2. entry_state:
   - One precise sentence: the EXACT visual state at frame zero of this scene
   - Scene 1: "opening shot — final vision/result already visible"
   - Scene 2: "cut to initial state/components — chronological sequence begins"
   - Scene 3: describe what is already done when we cut in (e.g., "journey has begun, ready for main action")
   - Scene 4: MUST list every action from scene 3 as already completed (e.g., "arrived at destination and completely settled — no motion")

3. narrator_text:
   - 1-2 sentences spoken aloud by an off-screen narrator, in {("Hebrew" if lang == "he" else "English")}
   - Conversational and warm tone; fits the scene's emotional beat
   - Example (food): "This is the moment everything comes together — rich tomato, fresh basil, and pasta cooked to perfection."

4. caption_text / caption_text_en:
   - caption_text: EXACT verbatim copy of narrator_text — word-for-word identical, same language. This is the on-screen subtitle the viewer reads while the narrator speaks.
   - caption_text_en: ALWAYS in English — concise 8-word version for Veo's internal text rendering prompt only
   - CRITICAL: caption_text MUST match narrator_text exactly. Do NOT write a different shorter phrase.

5. audio_mood:
   - Specify music energy + tempo + ambient sounds
   - Use abstract musical descriptors ONLY — no instrument names
   - 🚫 FORBIDDEN: "guitar", "piano", "drums", or any physical instrument name
   - Genre MUST stay consistent across all 4 scenes (energy can evolve)
   - Scene 3 audio MUST include a natural energy decrease toward the end to match the visual deceleration

════════════════════════════════════════
STRICT ANTI-HALLUCINATION RULES
════════════════════════════════════════
1. LOGICAL CONTINUITY (Context-Aware Elements): Elements must make logical sense for the specific category.
   - For "CLOSED" processes (like cooking, recipes, or product assembly): Do NOT introduce new ingredients, magical objects, or people not established in the first scenes. 
   - For "OPEN" journeys (like travel, real estate tours, or events): You MAY introduce new environments, landscapes, or objects (e.g., statues, landmarks, different rooms), but they MUST logically belong to the specific stated itinerary/location. No bizarre or out-of-context additions.
2. NO CROSS-MODALITY: visual_description must be 100% silent. Never describe sound, music, or smell inside a visual field.
3. FORWARD MOTION ONLY: within scenes 2-4, time and the journey move forward only. No rewinding, no undoing.
4. NO REPEAT ACTIONS: if a specific action or location was the focus in scene N, it CANNOT be the exact same focus in scene N+1.
5. SCENE 3 MUST DECELERATE: the last 3 seconds of scene 3 must be calm and nearly static.
6. SUBJECT LOCK: The "canonical_subject" (the core theme or main entity) must remain the central anchor across all scenes, even if the background or location completely changes.
7. ADAPT TO TOPIC: use terminology appropriate to the niche (e.g., culinary terms for food, geographical/architectural terms for travel and real estate).
8. SCENE 3 FULL ARC: Scene 3 MUST show a complete progression (initiation → main action/movement → settling still). Do NOT skip directly to the end of the action.
════════════════════════════════════════
OUTPUT FORMAT — CRITICAL
════════════════════════════════════════
Your response MUST be a single raw JSON object.
ABSOLUTELY FORBIDDEN: markdown fences, backticks, any text before {{ or after }}.
The first character MUST be {{ and the last MUST be }}.

{{
  "index": 0,
  "canonical_subject": "...",
  "visual_style_descriptor": "...",
  "content_category": "...",
  "scenes": [
    {{
      "scene": 1,
      "duration_sec": 8,
      "entry_state": "opening shot — finished result already visible",
      "visual_description": "[canonical_subject] — [finished result + components visible + fluid camera + lighting/mood]",
      "caption_text": "...",
      "caption_text_en": "...",
      "narrator_text": "...",
      "audio_mood": "..."
    }},
    {{
      "scene": 2,
      "duration_sec": 7,
      "entry_state": "cut to raw components/ingredients laid out — chronological sequence begins",
      "visual_description": "[canonical_subject] — [raw components laid out + first prep/action motion + fluid camera + lighting/mood]",
      "caption_text": "...",
      "caption_text_en": "...",
      "narrator_text": "...",
      "audio_mood": "..."
    }},
    {{
      "scene": 3,
      "duration_sec": 7,
      "entry_state": "components prepped and ready for main action",
      "visual_description": "[canonical_subject] — [main active transformation/process occurs + subject settles completely still at the end, fluid camera + lighting/mood]",
      "caption_text": "...",
      "caption_text_en": "...",
      "narrator_text": "...",
      "audio_mood": "... peak energy seconds 0-4, decreasing toward end"
    }},
    {{
      "scene": 4,
      "duration_sec": 7,
      "entry_state": "subject is fully complete and presented in its final environment",
      "visual_description": "[canonical_subject] — fully presented in its final state, [specific environmental details], camera slowly pushing in.",
      "caption_text": "...",
      "caption_text_en": "...",
      "narrator_text": "...",
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
    try:
        # ניקוי markdown
        cleaned = text.replace("```json", "").replace("```", "").strip()

        start_obj = cleaned.find('{')
        start_arr = cleaned.find('[')

        # אין JSON בכלל
        if start_obj == -1 and start_arr == -1:
            raise ValueError("No JSON start found")

        # בחירת התחלה נכונה
        if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
            start = start_arr
            end = cleaned.rfind(']')
        else:
            start = start_obj
            end = cleaned.rfind('}')

        # אם לא נמצא סוף
        if end == -1:
            raise ValueError("No JSON end found")

        json_str = cleaned[start:end + 1]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # LLMs sometimes emit literal control chars inside string values;
            # strict=False accepts them without corrupting the content.
            try:
                return json.loads(json_str, strict=False)
            except json.JSONDecodeError:
                # Last resort: collapse whitespace outside strings (structural noise).
                collapsed = re.sub(r"\s+", " ", json_str)
                return json.loads(collapsed)

    except Exception as exc:
        logger.error(
            "[ContentAgent] JSON parse error: %s\nRaw: %s",
            exc,
            text[:500]
        )
        raise json.JSONDecodeError(str(exc), text, 0)



def _extract_visual_style(parsed: Any) -> str:
    if isinstance(parsed, dict):
        return parsed.get("visual_style_descriptor", "")
    return ""


async def generate_style_fields(
    description: str,
    content_type: str,
    platform: str,
    language: str,
) -> tuple[str, str]:
    """Lightweight call — returns (visual_style_descriptor, content_category) only."""
    lang_hint = "Hebrew" if language == "he" else "English"
    prompt = f"""Analyze this content brief and return visual style information only.

TOPIC: "{description}"
PLATFORM: {platform}
CONTENT TYPE: {content_type}
LANGUAGE: {lang_hint}

Return ONLY a valid JSON object:
{{
  "visual_style_descriptor": "<one sentence max 25 words: lighting temperature, color palette, camera angle, depth of field, mood>",
  "content_category": "<1-2 words: if food/cooking/baking/recipe related use exactly 'food', otherwise the specific category>"
}}"""

    response = await complete(
        messages=[{"role": "user", "content": prompt}],
        system="You are a visual style analyst. Output ONLY valid JSON.",
        max_tokens=200,
    )
    try:
        parsed = _extract_json(response.content[0].text)
        if isinstance(parsed, dict):
            return (
                parsed.get("visual_style_descriptor", ""),
                parsed.get("content_category", ""),
            )
    except Exception as exc:
        logger.warning("[generate_style_fields] parse failed (%s) — returning empty", exc)
    return "", ""


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
    system = "You are an expert social media copywriter. Output ONLY valid JSON."

    if content_type == "comment":
        failed_items = [
            vr for vr in state.get("validation_results", [])
            if not vr.get("passed")
        ]
        if failed_items and state.get("retry_count", 0) > 0:
            # retry — ייצר רק את הכושלים
            prompt = _build_comments_retry_prompt(state, failed_items)
        else:
            # ריצה ראשונה — ייצר הכל
            prompt = _build_comments_prompt(state)
        prompt += retry_feedback
    elif content_type == "reels":
        prompt = _build_reels_script_prompt(state) + retry_feedback
        system = "You are an expert video script writer. Output ONLY valid JSON."
    else:
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
    content_category = ""
    if isinstance(parsed, dict):
        content_category = parsed.get("content_category", "")

    # Normalise → flat list
    if isinstance(parsed, dict):
        if content_type in ("post", "story") and "captions" in parsed:
            items = parsed["captions"]
        else:
            items = [parsed]
    else:
        items = parsed

    # במקרה של retry לcomments — מזג את התגובות החדשות עם הישנות
    if content_type == "comment" and state.get("retry_count", 0) > 0:
        existing = state.get("generated_texts", [])
        if existing and isinstance(items, list):
            # בנה dict מהקיימים
            merged = {item.get("index", i): item for i, item in enumerate(existing)}
            # החלף רק את הכושלים
            for new_item in items:
                idx = new_item.get("index")
                if idx is not None:
                    merged[idx] = new_item
            items = [merged[k] for k in sorted(merged.keys())]
            logger.info(
                "[%s] ContentAgent: merged retry — total=%d",
                task_id, len(items),
            )

    s3_key = asset_key(task_id, platform, content_type, item_index, "content.json")
    await upload_json(s3_key, items)

    logger.info(
        "[%s] ContentAgent: item_%d generated %d item(s) cost=$%.4f",
        task_id, item_index, len(items), cost,
    )
  
    is_retry = state.get("retry_count", 0) > 0
    is_video_checkpoint = bool(state.get("current_video_ref"))

    updates: dict = {
        "generated_texts":   items,
        "cost_accumulated":  state.get("cost_accumulated", 0.0) + cost,
        "generated_images":  state.get("generated_images", []) if (is_retry and content_type in ("post", "story")) or is_video_checkpoint else [],
        "generated_videos": state.get("generated_videos", []) if is_video_checkpoint else [],
        "current_video_ref": state.get("current_video_ref") if is_video_checkpoint else None,
        "completed_extends": state.get("completed_extends", 0) if is_video_checkpoint else 0,
        "all_video_refs":    state.get("all_video_refs", []) if is_video_checkpoint else [],
        "content_category":  state.get("content_category", ""),
    }

    # visual_style_descriptor: first item sets the anchor; subsequent items keep
    # whatever is already in state (passed in from runner via style_reference_image).
    if visual_style_descriptor and not state.get("visual_style_descriptor"):
        updates["visual_style_descriptor"] = visual_style_descriptor
    if content_category and not state.get("content_category"):
            updates["content_category"] = content_category
    return updates


