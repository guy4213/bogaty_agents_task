from __future__ import annotations
import json
import logging
import re
from typing import Any

from app.config import get_settings
from app.graph.state import ContentEngineState
from app.services.claude_client import complete, estimate_cost

logger = logging.getLogger(__name__)

from app.constants import CAPTION_LIMITS, HASHTAG_LIMITS
VIDEO_DURATION_LIMITS = {
    "tiktok":    (15, 180),
    "instagram": (3, 90),
    "facebook":  (1, 240),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))

def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta and not tb:
        return 1.0
    union = len(ta | tb)
    return len(ta & tb) / union if union else 0.0

def _check_batch_uniqueness(texts: list[str], threshold: float) -> list[tuple[int, int, float]]:
    violations = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            score = _jaccard(texts[i], texts[j])
            if score >= threshold:
                violations.append((i, j, round(score, 3)))
    return violations

def _detect_language(text: str) -> str:
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return "unknown"

def _is_reel_script(text_item: dict) -> bool:
    """Reel scripts have 'scenes' key — they are not plain text items."""
    return "scenes" in text_item

def _validate_text_item(
    text_item: dict, platform: str, content_type: str, expected_lang: str
) -> list[str]:
    if _is_reel_script(text_item):
        errors = []
        scenes = text_item.get("scenes", [])
        if not scenes:
            errors.append("Reel script missing scenes")
        for s in scenes:
            # עברית — בדוק caption_text
            # אנגלית — בדוק caption_text_en
            if expected_lang == "he":
                if not s.get("caption_text"):
                    errors.append(f"Scene {s.get('scene', '?')} missing caption_text")
            else:
                if not s.get("caption_text_en"):
                    errors.append(f"Scene {s.get('scene', '?')} missing caption_text_en")
        return errors
    errors   = []
    text     = text_item.get("text", "")
    hashtags = text_item.get("hashtags", [])

    if not text.strip():
        errors.append("Empty text content")
        return errors

    detected      = _detect_language(text)
    detected_norm = "he" if detected in ("he", "iw") else detected
    if detected_norm != expected_lang:
        errors.append(f"Language mismatch: expected={expected_lang} detected={detected_norm}")

    char_limit = CAPTION_LIMITS.get(platform, 2200)
    if len(text) > char_limit:
        errors.append(f"Caption too long: {len(text)} > {char_limit} chars")

    ht_limit = HASHTAG_LIMITS.get(platform, 30)
    if ht_limit > 0 and len(hashtags) > ht_limit:
        errors.append(f"Too many hashtags: {len(hashtags)} > {ht_limit}")

    return errors

def _validate_image_item(image_item: dict, platform: str, content_type: str) -> list[str]:
    return [] if image_item.get("s3_key") else ["Image missing S3 key"]


def _validate_video_item(
    video_item: dict, platform: str, lang: str = "he"
) -> list[str]:
    errors = []

    # S3 key — חובה מוחלטת
    if not video_item.get("s3_key"):
        errors.append("Video missing S3 key")
        return errors  # אין טעם לבדוק שאר אם אין קובץ

    # Duration
    duration         = video_item.get("duration_sec", 0)
    min_dur, max_dur = VIDEO_DURATION_LIMITS.get(platform, (1, 600))
    if duration < min_dur or duration > max_dur:
        errors.append(
            f"Video duration {duration}s out of range [{min_dur}s, {max_dur}s]"
        )

    # Captions — חובה, אבל שדה שונה לפי שפה
    if not video_item.get("has_captions"):
        if lang == "he":
            errors.append(
                "Hebrew captions missing — caption_text absent in one or more scenes"
            )
        else:
            errors.append(
                "English captions missing — caption_text_en absent in one or more scenes"
            )

    # has_audio — warning בלבד, לא failure
    if not video_item.get("has_audio"):
        logger.warning(
            "Video has_audio=False — metadata issue, non-fatal for platform=%s",
            platform,
        )

    return errors

# ---------------------------------------------------------------------------
# LLM quality gate — ONE batch call for all texts
# ---------------------------------------------------------------------------

_QUALITY_SYSTEM = (
    "You are a strict content quality evaluator for social media. "
    "Respond ONLY with valid JSON — no preamble, no markdown fences."
)

_BATCH_QUALITY_PROMPT = """Evaluate these {n} {content_type}(s) for {platform} (language: {language}).
Topic: "{description}"

Items:
{items_block}

Score each 1-10 on:
1. Natural, human-sounding (not AI-generated)
2. Tone matches {platform} ({content_type})
3. Relevant to the topic
4. No spam, offensive content, or errors

Score below 6 = reject. Be strict.

Return ONLY a JSON array — one object per item in order:
[{{"index": 0, "score": 8, "issues": [], "feedback": ""}}]"""


async def _llm_quality_check_batch(
    texts: list[str],
    platform: str,
    content_type: str,
    language: str,
    description: str,
) -> tuple[list[dict], float]:
    if not texts:
        return [], 0.0

    items_block = "\n".join(f'[{i}]: "{t[:400]}"' for i, t in enumerate(texts))
    prompt = _BATCH_QUALITY_PROMPT.format(
        n=len(texts), content_type=content_type, platform=platform,
        language=language, description=description, items_block=items_block,
    )

    response = await complete(
        messages=[{"role": "user", "content": prompt}],
        system=_QUALITY_SYSTEM,
        max_tokens=min(256 * len(texts), 4096),
    )

    cost = estimate_cost(response)
    raw  = response.content[0].text

    try:
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        results = json.loads(cleaned)
        if not isinstance(results, list):
            raise ValueError("Expected JSON array")
        return results, cost
    except Exception as exc:
        logger.warning("Batch LLM quality check parse failed (%s) — defaulting score=7", exc)
        return [{"index": i, "score": 7, "issues": [], "feedback": ""} for i in range(len(texts))], cost


# ---------------------------------------------------------------------------
# Main validator node
# ---------------------------------------------------------------------------

async def run(state: ContentEngineState) -> dict:
    cfg          = get_settings()
    task_id      = state["task_id"]
    item_index   = state["item_index"]
    platform     = state["platform"]
    content_type = state["content_type"]
    language     = state["language"]
    description  = state["description"]
    retry_count  = state.get("retry_count", 0)
    threshold    = cfg.jaccard_similarity_threshold
    min_score    = cfg.content_validator_min_score

    logger.info("[%s] ContentValidator: item_%d retry=%d", task_id, item_index, retry_count)

    validation_results:  list[dict] = []
    all_passed           = True
    total_validator_cost = 0.0

    texts  = state.get("generated_texts",  [])
    images = state.get("generated_images", [])
    videos = state.get("generated_videos", [])

    # ------------------------------------------------------------------
    # 1. Text — deterministic checks
    # ------------------------------------------------------------------
    plain_text_strings = [
        t.get("text", "") for t in texts
        if isinstance(t, dict) and not _is_reel_script(t)
    ]
    if len(plain_text_strings) > 1:
        for i, j, score in _check_batch_uniqueness(plain_text_strings, threshold):
            logger.warning("[%s] Uniqueness violation: items %d & %d jaccard=%.3f", task_id, i, j, score)
            validation_results.append({
                "item_id": i, "passed": False, "score": 0,
                "errors": [f"Near-duplicate of item {j} (jaccard={score})"],
                "retry_feedback": f"Item {i} too similar to item {j}. Rewrite with a clearly different angle.",
            })
            all_passed = False

    det_passed_indices: list[int] = []
    for idx, text_item in enumerate(texts):
        if not isinstance(text_item, dict):
            continue
        det_errors = _validate_text_item(text_item, platform, content_type, language)
        if det_errors:
            validation_results.append({
                "item_id": idx, "passed": False, "score": 0,
                "errors": det_errors,
                "retry_feedback": f"Fix: {'; '.join(det_errors)}",
            })
            all_passed = False
        else:
            det_passed_indices.append(idx)

    # LLM batch check — only for plain text items (skip reel scripts)
    plain_passed_indices = [
        i for i in det_passed_indices
        if not _is_reel_script(texts[i])
    ]
    if plain_passed_indices:
        batch_texts = [texts[i].get("text", "") for i in plain_passed_indices]
        llm_results, llm_cost = await _llm_quality_check_batch(
            batch_texts, platform, content_type, language, description,
        )
        total_validator_cost += llm_cost

        for result_idx, original_idx in enumerate(plain_passed_indices):
            llm    = llm_results[result_idx] if result_idx < len(llm_results) else {}
            score  = llm.get("score", 7)
            issues = llm.get("issues", [])
            passed = score >= min_score
            if not passed:
                all_passed = False
                logger.warning(
                    "[%s] ContentValidator: item_%d text[%d] FAILED score=%d",
                    task_id, item_index, original_idx, score,
                )
            validation_results.append({
                "item_id": original_idx, "passed": passed, "score": score,
                "errors": issues,
                "retry_feedback": llm.get("feedback", "") if not passed else "",
            })

    # Reel script items that passed deterministic check → mark as passed
    reel_passed_indices = [i for i in det_passed_indices if _is_reel_script(texts[i])]
    for idx in reel_passed_indices:
        validation_results.append({
            "item_id": idx, "passed": True, "score": 10, "errors": [], "retry_feedback": "",
        })

    # ------------------------------------------------------------------
    # 2. Image checks
    # ------------------------------------------------------------------
    for idx, image_item in enumerate(images):
        img_errors = _validate_image_item(image_item, platform, content_type)
        passed     = len(img_errors) == 0
        if not passed:
            all_passed = False
        validation_results.append({
            "item_id": f"image_{idx}", "passed": passed,
            "score": 10 if passed else 0, "errors": img_errors,
            "retry_feedback": "; ".join(img_errors) if img_errors else "",
        })

    # ------------------------------------------------------------------
    # 3. Video checks
    # ------------------------------------------------------------------
    for idx, video_item in enumerate(videos):
        vid_errors = _validate_video_item(video_item, platform, language)
        passed     = len(vid_errors) == 0
        if not passed:
            all_passed = False
        validation_results.append({
            "item_id": f"video_{idx}", "passed": passed,
            "score": 10 if passed else 0, "errors": vid_errors,
            "retry_feedback": "; ".join(vid_errors) if vid_errors else "",
        })

    # ------------------------------------------------------------------
    # 4. Required assets check
    # ------------------------------------------------------------------
    pipeline_type = state.get("pipeline_type", "text_only")
    if pipeline_type == "text_image" and not images:
        all_passed = False
        validation_results.append({
            "item_id": "assets", "passed": False, "score": 0,
            "errors": ["Missing required image for text_image pipeline"],
            "retry_feedback": "Image generation must complete before validation.",
        })
    if pipeline_type == "full_video" and not videos:
        all_passed = False
        validation_results.append({
            "item_id": "assets", "passed": False, "score": 0,
            "errors": ["Missing required video for full_video pipeline"],
            "retry_feedback": "Video generation must complete before validation.",
        })

    # ------------------------------------------------------------------
    # 5. Status + retry counter
    # ------------------------------------------------------------------
    max_retries     = cfg.max_retries_per_item
    new_retry_count = retry_count

    if not all_passed and retry_count < max_retries:
        new_retry_count = retry_count + 1
        logger.info(
            "[%s] ContentValidator: FAILED — retry %d/%d scheduled",
            task_id, new_retry_count, max_retries,
        )

    # FIX: "processing" = graph will retry via content_agent (retry_count < max_retries)
    #      "partial"    = retries exhausted, item delivered as-is
    #      "completed"  = all checks passed
    if all_passed:
        final_status = "completed"
    elif new_retry_count < max_retries:
        final_status = "processing"   # graph router → content_agent
    else:
        final_status = "partial"      # exhausted, move on

    passed_count = sum(1 for vr in validation_results if vr.get("passed"))
    logger.info(
        "[%s] ContentValidator: item_%d passed=%d/%d all_passed=%s status=%s cost=$%.4f",
        task_id, item_index, passed_count, len(validation_results),
        all_passed, final_status, total_validator_cost,
    )
    failed_results = [vr for vr in validation_results if not vr.get("passed")]
    if failed_results:
        logger.warning(
            "[%s] ContentValidator: FAILED details — %s",
            task_id,
            json.dumps(failed_results, ensure_ascii=False, indent=2),
        )
    return {
        "validation_results": validation_results,
        "retry_count":        new_retry_count,
        "status":             final_status,
        "cost_accumulated":   state.get("cost_accumulated", 0.0) + total_validator_cost,
    }



