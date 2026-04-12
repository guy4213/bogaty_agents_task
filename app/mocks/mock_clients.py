from __future__ import annotations
import json
import logging
import pathlib
import struct
import zlib

logger = logging.getLogger(__name__)

_LOCAL_S3_ROOT = pathlib.Path("/tmp/content-engine-dry-run")


# ---------------------------------------------------------------------------
# Mock Claude
# ---------------------------------------------------------------------------

class MockClaudeMessage:
    def __init__(self, text: str):
        self.content = [type("Block", (), {"text": text})()]
        self.usage   = type("Usage", (), {"input_tokens": 500, "output_tokens": 300})()


def _make_comments(quantity: int, lang: str) -> str:
    personas = [
        "food_blogger", "home_cook", "nutrition_enthusiast", "skeptical_commenter",
        "cooking_beginner", "professional_chef", "busy_parent", "student_budget",
        "food_photographer", "diet_conscious",
    ]
    texts_he = [
        "וואו, זה נראה מדהים! חייבת לנסות את המתכון הזה.",
        "פסטה מושלמת! כזו שאי אפשר לעצור לאכול.",
        "נראה טעים, אבל כמה קלוריות יש פה בערך?",
        "לא בטוחה שאני אצליח לשחזר את זה בבית...",
        "מתכון פשוט ויפה, תודה שהשתפת!",
        "הרוטב נראה קצת דליל לטעמי, אבל הפרזנטציה יפה.",
        "בדיוק מה שהייתי צריכה להכין לילדים הלילה!",
        "אפשר להכין את זה בתקציב של 20 שקל?",
        "הצבעים במנה הזו פשוט מושלמים לצילום!",
        "מצוין לדיאטה? יש כאן הרבה פחמימות...",
        "המנה הזו מזכירה לי את סבתא שלי, כל כך נוסטלגי!",
        "חייב לנסות את זה עם גבינת פרמזן איכותית.",
        "נראה מעולה! כמה זמן לוקח להכין?",
        "הכנתי את זה אמש וכל המשפחה אהבה!",
        "פסטה טרייה או יבשה? זה הסוד כנראה.",
    ]
    texts_en = [
        "This looks absolutely amazing! I need to try this recipe.",
        "Perfect pasta! The kind you just can't stop eating.",
        "Looks delicious, but roughly how many calories is this?",
        "Not sure I can recreate this at home, but I'll try!",
        "Such a simple and beautiful recipe, thanks for sharing!",
        "The sauce looks a bit thin for my taste, but great presentation.",
        "Exactly what I needed to make for the kids tonight!",
        "Can this be made on a $10 budget?",
        "The colors in this dish are just perfect for photography!",
        "Good for dieting? Seems like a lot of carbs...",
        "This reminds me of my grandmother's cooking, so nostalgic!",
        "Must try this with some quality parmesan on top.",
        "Looks amazing! How long does it take to make?",
        "Made this last night and the whole family loved it!",
        "Fresh pasta or dried? That's probably the secret.",
    ]
    texts = texts_he if lang == "he" else texts_en

    return json.dumps([
        {
            "index":   idx,
            "text":    texts[idx % len(texts)],
            "persona": personas[idx % len(personas)],
        }
        for idx in range(quantity)
    ])


def _make_single_caption(item_index: int, lang: str, platform: str) -> str:
    """
    FIX: returns ONE caption for the given item_index angle.
    Previously _make_captions() returned `quantity` captions and the
    image_agent always used index 0 → all items got the same angle.
    """
    angles   = [
        "restaurant ambiance and atmosphere",
        "close-up of the dish and ingredients",
        "the overall dining experience and mood",
        "behind-the-scenes / preparation story",
        "personal connection / why this meal matters",
    ]
    texts_he = [
        "ארוחת ערב מושלמת במסעדה שמביאה אותך חזרה לאיטליה.",
        "פסטה ביתית עם רוטב עגבניות טרי — פשוט אבל מושלם.",
        "חוויה קולינרית שכדאי לחזור אליה שוב ושוב.",
        "מאחורי הקלעים: כך נולדת המנה המושלמת.",
        "כל ביס מזכיר לי ארוחות משפחתיות של פעם.",
    ]
    texts_en = [
        "A perfect dinner that takes you straight back to Italy.",
        "Handmade pasta with fresh tomato sauce — simple but perfect.",
        "A culinary experience worth coming back to again and again.",
        "Behind the scenes: how the perfect dish was born.",
        "Every bite reminds me of family dinners growing up.",
    ]
    texts    = texts_he if lang == "he" else texts_en
    hashtags = ["#pasta", "#italianfood", "#foodphotography", "#restaurant", "#foodie"]

    return json.dumps({
        "visual_style_descriptor": (
            "Warm candlelit tones, rich ochre palette, shallow DOF close-up, intimate mood."
        ),
        "captions": [
            {
                "index":    0,
                "text":     texts[item_index % len(texts)],
                "hashtags": hashtags,
                "angle":    angles[item_index % len(angles)],
            }
        ],
    })


def _make_reel_script(lang: str) -> str:
    # FIX: every scene now includes caption_text_en for Veo rendering
    if lang == "he":
        scenes = [
            {
                "scene": 1, "duration_sec": 8,
                "visual_description": "ידיים קוצצות עגבניות טריות על לוח עץ",
                "caption_text":    "מרכיבים טריים בלבד",
                "caption_text_en": "Fresh ingredients only",   # ← FIX
                "audio_mood": "אווירה רגועה של מטבח",
            },
            {
                "scene": 2, "duration_sec": 7,
                "visual_description": "פסטה מתבשלת בסיר עם קיטור עולה",
                "caption_text":    "מבשלים עם אהבה",
                "caption_text_en": "Cooking with love",        # ← FIX
                "audio_mood": "צלילי מטבח",
            },
            {
                "scene": 3, "duration_sec": 7,
                "visual_description": "הגשת הפסטה על צלחת לבנה עם ריחן",
                "caption_text":    "פרזנטציה מושלמת",
                "caption_text_en": "Perfect presentation",     # ← FIX
                "audio_mood": "מוזיקה עדינה",
            },
            {
                "scene": 4, "duration_sec": 7,
                "visual_description": "צילום תקריב של המנה המוגמרת",
                "caption_text":    "תנסו בבית!",
                "caption_text_en": "Try this at home!",        # ← FIX
                "audio_mood": "מוזיקה עליזה",
            },
        ]
        caption = "פסטה ביתית שתשגע אתכם 🍝"
    else:
        scenes = [
            {
                "scene": 1, "duration_sec": 8,
                "visual_description": "Hands chopping fresh tomatoes on a wooden board",
                "caption_text":    "Fresh ingredients only",
                "caption_text_en": "Fresh ingredients only",
                "audio_mood": "Calm kitchen ambience",
            },
            {
                "scene": 2, "duration_sec": 7,
                "visual_description": "Pasta boiling in pot with rising steam",
                "caption_text":    "Cooking with love",
                "caption_text_en": "Cooking with love",
                "audio_mood": "Kitchen sounds",
            },
            {
                "scene": 3, "duration_sec": 7,
                "visual_description": "Plating pasta on white dish with basil",
                "caption_text":    "Perfect presentation",
                "caption_text_en": "Perfect presentation",
                "audio_mood": "Soft music",
            },
            {
                "scene": 4, "duration_sec": 7,
                "visual_description": "Close-up beauty shot of finished dish",
                "caption_text":    "Try this at home!",
                "caption_text_en": "Try this at home!",
                "audio_mood": "Upbeat music",
            },
        ]
        caption = "Homemade pasta that will blow your mind 🍝"

    return json.dumps({
        "index":                   0,
        "visual_style_descriptor": "Warm golden-hour tones, steam rising close-ups, slow push-in camera, vibrant appetizing mood.",
        "scenes":                  scenes,
        "hashtags":                ["#pasta", "#homecooking", "#reels", "#foodvideo"],
        "full_caption":            caption,
    })


async def mock_claude_complete(messages: list, system: str = "", max_tokens: int = 4096):
    prompt = messages[-1]["content"] if messages else ""
    lang   = "he" if "Hebrew" in prompt else "en"

    if "comment" in prompt.lower():
        quantity = 3
        for line in prompt.split("\n"):
            if "Generate exactly" in line:
                try:
                    quantity = int(line.split("Generate exactly")[1].split()[0])
                except Exception:
                    pass
        text = _make_comments(quantity, lang)

    elif "scenes" in prompt.lower() or "reel" in prompt.lower() or "script" in system.lower():
        text = _make_reel_script(lang)

    elif "caption" in prompt.lower():
        # FIX: extract item_index from prompt so each mock returns the right angle
        item_index = 0
        for line in prompt.split("\n"):
            if "item_index:" in line.lower():
                try:
                    item_index = int(line.split(":")[1].strip())
                except Exception:
                    pass
        platform = "instagram"
        for p in ["instagram", "tiktok", "twitter", "telegram", "facebook"]:
            if p in prompt.lower():
                platform = p
                break
        text = _make_single_caption(item_index, lang, platform)

    elif "evaluate" in prompt.lower() or "score" in prompt.lower():
        text = json.dumps({
            "scores": [],  # batch format — see content_validator.py
            "overall_feedback": "Content looks natural and on-brand.",
        })
        # fallback for legacy single-item evaluate calls
        text = json.dumps({"score": 8, "issues": [], "feedback": "Content looks natural and on-brand."})

    else:
        text = json.dumps([{"index": 0, "text": "Mock content.", "persona": "food_blogger"}])

    logger.info("[DRY_RUN] MockClaude: %d chars", len(text))
    return MockClaudeMessage(text)


# ---------------------------------------------------------------------------
# Mock Image
# ---------------------------------------------------------------------------

def _make_png() -> bytes:
    def chunk(t: bytes, d: bytes) -> bytes:
        return (
            struct.pack(">I", len(d)) + t + d
            + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        )
    sig  = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
    raw  = b"".join(b"\x00" + b"\xFF\x80\x20" * 8 for _ in range(8))
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


async def mock_generate_image(
    prompt: str,
    aspect_ratio: str = "1:1",
    style_reference_bytes: bytes | None = None,
    visual_style_descriptor: str = "",
) -> bytes:
    logger.info(
        "[DRY_RUN] MockImage ratio=%s has_ref=%s",
        aspect_ratio, style_reference_bytes is not None,
    )
    return _make_png()


# ---------------------------------------------------------------------------
# Mock Video
# ---------------------------------------------------------------------------

_counter = 0


async def mock_generate_video_initial(prompt: str) -> str:
    global _counter
    _counter += 1
    uri = f"mock://veo/initial_{_counter}"
    logger.info("[DRY_RUN] MockVeo initial: %s", uri)
    return uri


async def mock_extend_video(video_uri: str, prompt: str, extend_index: int) -> str:
    global _counter
    _counter += 1
    uri = f"mock://veo/extend_{_counter}"
    logger.info("[DRY_RUN] MockVeo extend #%d: %s", extend_index + 1, uri)
    return uri


async def mock_download_video(video_uri: str) -> bytes:
    logger.info("[DRY_RUN] MockVeo download: %s", video_uri)
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"


# ---------------------------------------------------------------------------
# Mock S3
# ---------------------------------------------------------------------------

async def mock_upload_bytes(key: str, data: bytes, content_type: str = "") -> str:
    path = _LOCAL_S3_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    logger.info("[DRY_RUN] MockS3 wrote %d bytes -> %s", len(data), path)
    return key


async def mock_presigned_url(key: str, expiry_sec: int = 3600) -> str:
    return f"file://{_LOCAL_S3_ROOT / key}"
async def mock_burn_hebrew_captions(
    video_bytes: bytes,
    scenes: list,
    initial_duration: int,
    extend_duration: int,
) -> bytes:
    """Mock FFmpeg caption burning — returns video bytes unchanged."""
    logger.info("[DRY_RUN] MockFFmpeg: skipping Hebrew caption burn (%d bytes)", len(video_bytes))
    return video_bytes