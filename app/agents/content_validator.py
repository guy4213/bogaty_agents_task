from __future__ import annotations
import json
import logging
import re
from typing import Any

from app.config import get_settings
from app.graph.state import ContentEngineState
from app.services.claude_client import complete, estimate_cost

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform limits (deterministic rules)
# ---------------------------------------------------------------------------

CAPTION_LIMITS = {
    "instagram": 2200,
    "tiktok":    2200,
    "twitter":   280,
    "telegram":  4096,
    "facebook":  63206,
}

HASHTAG_LIMITS = {
    "instagram": 30,
    "tiktok":    30,
    "twitter":   5,
    "telegram":  0,
    "facebook":  10,
}

VIDEO_DURATION_LIMITS = {
    "tiktok":    (15, 180),
    "instagram": (3, 90),
    "facebook":  (1, 240),
}


# ---------------------------------------------------------------------------
# Jaccard similarity
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta and not tb:
        return 1.0
    intersection = len(ta & tb)
    union = len(ta | tb)
    return intersection / union if union else 0.0


def _check_batch_uniqueness(texts: list[str], threshold: float) -> list[tuple[int, int, float]]:
    """Return list of (i, j, score) pairs that exceed the similarity threshold."""
    violations = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            score = _jaccard(texts[i], texts[j])
            if score >= threshold:
                violations.append((i, j, round(score, 3)))
    return violations


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def _detect_language(text: str) -> str:
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Deterministic validation
# ---------------------------------------------------------------------------

def _validate_text_item(
    text_item: dict,
    platform: str,
    content_type: str,
    expected_lang: str,
) -> list[str]:
    """Returns list of error strings. Empty = passed."""
    errors: list[str] = []
    text = text_item.get("text", "")
    hashtags = text_item.get("hashtags", [])

    # Language check
    if text.strip():
        detected = _detect_language(text)
        # langdetect uses 'iw' for Hebrew; normalise
        detected_norm = "he" if detected in ("he", "iw") else detected
        if detected_norm != expected_lang:
            errors.append(
                f"Language mismatch: expected={expected_lang} detected={detected_norm}"
            )

    # Caption length
    char_limit = CAPTION_LIMITS.get(platform, 2200)
    if len(text) > char_limit:
        errors.append(f"Caption too long: {len(text)} > {char_limit} chars")

    # Hashtag count
    ht_limit = HASHTAG_LIMITS.get(platform, 30)
    if ht_limit > 0 and len(hashtags) > ht_limit:
        errors.append(f"Too many hashtags: {len(hashtags)} > {ht_limit}")

    # Empty content
    if not text.strip():
        errors.append("Empty text content")

    return errors


def _validate_image_item(image_item: dict, platform: str, content_type: str) -> list[str]:
    errors: list[str] = []
    if not image_item.get("s3_key"):
        errors.append("Image missing S3 key")
    return errors


def _validate_video_item(video_item: dict, platform: str) -> list[str]:
    errors: list[str] = []
    duration = video_item.get("duration_sec", 0)
    min_dur, max_dur = VIDEO_DURATION_LIMITS.get(platform, (1, 600))

    if duration < min_dur or duration > max_dur:
        errors.append(
            f"Video duration {duration}s out of range [{min_dur}s, {max_dur}s] for {platform}"
        )
    if not video_item.get("has_captions"):
        errors.append("Video missing embedded captions")
    if not video_item.get("has_audio"):
        errors.append("Video missing audio")
    if not video_item.get("s3_key"):
        errors.append("Video missing S3 key")

    return errors


# ---------------------------------------------------------------------------
# LLM quality gate
# ---------------------------------------------------------------------------

_QUALITY_SYSTEM = (
    "You are a strict content quality evaluator for social media. "
    "Respond ONLY with valid JSON — no preamble, no markdown fences."
)

_QUALITY_PROMPT_TEMPLATE = """Evaluate this {content_type} for {platform} (language: {language}):

---
{content}
---

Score it 1-10 on these criteria:
1. Natural, human-sounding (not AI-generated)
2. Tone matches {platform} ({content_type})
3. Relevant to: "{description}"
4. No spam patterns, offensive content, or factual errors

Return ONLY a JSON object:
{{"score": 7, "issues": ["specific issue 1", "specific issue 2"], "feedback": "concise fix suggestion"}}

Score below 6 = reject. Be strict."""


async def _llm_quality_check(
    content: str,
    platform: str,
    content_type: str,
    language: str,
    description: str,
) -> dict[str, Any]:
    prompt = _QUALITY_PROMPT_TEMPLATE.format(
        content_type=content_type,
        platform=platform,
        language=language,
        content=content[:2000],  # truncate to avoid token overflow
        description=description,
    )

    response = await complete(
        messages=[{"role": "user", "content": prompt}],
        system=_QUALITY_SYSTEM,
        max_tokens=256,
    )

    cost = estimate_cost(response)
    raw = response.content[0].text

    try:
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        result = json.loads(cleaned)
        result["cost"] = cost
        return result
    except json.JSONDecodeError:
        logger.warning("LLM quality gate JSON parse failed: %s", raw[:200])
        return {"score": 5, "issues": ["parse error"], "feedback": "Could not parse quality response", "cost": cost}


# ---------------------------------------------------------------------------
# Main validator node
# ---------------------------------------------------------------------------

async def run(state: ContentEngineState) -> dict:
    cfg = get_settings()
    task_id = state["task_id"]
    item_index = state["item_index"]
    platform = state["platform"]
    content_type = state["content_type"]
    language = state["language"]
    description = state["description"]
    retry_count = state.get("retry_count", 0)
    threshold = cfg.jaccard_similarity_threshold
    min_score = cfg.content_validator_min_score

    logger.info(
        "[%s] ContentValidator: item_%d retry=%d",
        task_id, item_index, retry_count,
    )

    validation_results: list[dict] = []
    all_passed = True
    total_validator_cost = 0.0

    texts = state.get("generated_texts", [])
    images = state.get("generated_images", [])
    videos = state.get("generated_videos", [])

    # ------------------------------------------------------------------
    # 1. Text items — deterministic checks
    # ------------------------------------------------------------------
    text_strings = [t.get("text", "") for t in texts if isinstance(t, dict)]

    # Batch uniqueness across all text items
    if len(text_strings) > 1:
        violations = _check_batch_uniqueness(text_strings, threshold)
        if violations:
            for i, j, score in violations:
                logger.warning(
                    "[%s] Uniqueness violation: items %d & %d jaccard=%.3f",
                    task_id, i, j, score,
                )
                validation_results.append({
                    "item_id": i,
                    "passed": False,
                    "score": 0,
                    "errors": [f"Near-duplicate of item {j} (jaccard={score})"],
                    "retry_feedback": f"Item {i} is too similar to item {j} (similarity={score:.2f}). Rewrite with a clearly different perspective.",
                })
                all_passed = False

    for idx, text_item in enumerate(texts):
        if not isinstance(text_item, dict):
            continue

        det_errors = _validate_text_item(text_item, platform, content_type, language)

        if det_errors:
            validation_results.append({
                "item_id": idx,
                "passed": False,
                "score": 0,
                "errors": det_errors,
                "retry_feedback": f"Fix these issues: {'; '.join(det_errors)}",
            })
            all_passed = False
            continue

        # LLM quality gate (only if deterministic passed)
        content_for_review = text_item.get("text", "")
        if text_item.get("hashtags"):
            content_for_review += "\n\nHashtags: " + " ".join(text_item["hashtags"])

        try:
            quality = await _llm_quality_check(
                content=content_for_review,
                platform=platform,
                content_type=content_type,
                language=language,
                description=description,
            )
            total_validator_cost += quality.get("cost", 0.0)
        except Exception as exc:
            logger.warning("[%s] LLM quality check failed: %s — passing by default", task_id, exc)
            quality = {"score": 7, "issues": [], "feedback": "", "cost": 0.0}

        score = quality.get("score", 0)
        issues = quality.get("issues", [])
        passed = score >= min_score

        if not passed:
            all_passed = False
            logger.warning(
                "[%s] ContentValidator: item_%d text idx=%d FAILED score=%d issues=%s",
                task_id, item_index, idx, score, issues,
            )

        validation_results.append({
            "item_id": idx,
            "passed": passed,
            "score": score,
            "errors": issues,
            "retry_feedback": quality.get("feedback", "") if not passed else "",
        })

    # ------------------------------------------------------------------
    # 2. Image items — deterministic checks
    # ------------------------------------------------------------------
    for idx, image_item in enumerate(images):
        img_errors = _validate_image_item(image_item, platform, content_type)
        passed = len(img_errors) == 0
        if not passed:
            all_passed = False
        validation_results.append({
            "item_id": f"image_{idx}",
            "passed": passed,
            "score": 10 if passed else 0,
            "errors": img_errors,
            "retry_feedback": "; ".join(img_errors) if img_errors else "",
        })

    # ------------------------------------------------------------------
    # 3. Video items — deterministic checks
    # ------------------------------------------------------------------
    for idx, video_item in enumerate(videos):
        vid_errors = _validate_video_item(video_item, platform)
        passed = len(vid_errors) == 0
        if not passed:
            all_passed = False
        validation_results.append({
            "item_id": f"video_{idx}",
            "passed": passed,
            "score": 10 if passed else 0,
            "errors": vid_errors,
            "retry_feedback": "; ".join(vid_errors) if vid_errors else "",
        })

    # ------------------------------------------------------------------
    # 4. Required assets present check
    # ------------------------------------------------------------------
    pipeline_type = state.get("pipeline_type", "text_only")
    if pipeline_type == "text_image" and not images:
        all_passed = False
        validation_results.append({
            "item_id": "assets",
            "passed": False,
            "score": 0,
            "errors": ["Missing required image for text_image pipeline"],
            "retry_feedback": "Image generation must complete before validation.",
        })
    if pipeline_type == "full_video" and not videos:
        all_passed = False
        validation_results.append({
            "item_id": "assets",
            "passed": False,
            "score": 0,
            "errors": ["Missing required video for full_video pipeline"],
            "retry_feedback": "Video generation must complete before validation.",
        })

    # ------------------------------------------------------------------
    # 5. Retry logic
    # ------------------------------------------------------------------
    max_retries = cfg.max_retries_per_item
    new_retry_count = retry_count

    if not all_passed and retry_count < max_retries:
        new_retry_count = retry_count + 1
        logger.info(
            "[%s] ContentValidator: item_%d FAILED — queuing retry %d/%d",
            task_id, item_index, new_retry_count, max_retries,
        )
        # Validation feedback is embedded in validation_results and will be
        # picked up by Content Agent on the next graph invocation.

    final_status = "completed" if all_passed else (
        "partial" if retry_count >= max_retries else "processing"
    )

    passed_count = sum(1 for vr in validation_results if vr.get("passed"))
    logger.info(
        "[%s] ContentValidator: item_%d passed=%d/%d all_passed=%s cost=$%.4f",
        task_id, item_index, passed_count, len(validation_results), all_passed, total_validator_cost,
    )

    return {
        "validation_results": validation_results,
        "retry_count": new_retry_count,
        "status": final_status,
        "cost_accumulated": state.get("cost_accumulated", 0.0) + total_validator_cost,
    }