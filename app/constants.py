from __future__ import annotations

CAPTION_LIMITS: dict[str, int] = {
    "instagram": 2200,
    "tiktok":    2200,
    "twitter":   280,
    "telegram":  4096,
    "facebook":  63206,
}

HASHTAG_LIMITS: dict[str, int] = {
    "instagram": 30,
    "tiktok":    30,
    "twitter":   5,
    "telegram":  0,
    "facebook":  10,
}
