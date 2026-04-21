from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

_VOICE_MAP = {
    "he": ("he-IL", "he-IL-Wavenet-B"),
    "en": ("en-US", "en-US-Wavenet-D"),
}


def synthesize(text: str, lang: str = "he") -> bytes:
    """Return MP3 bytes for text using Google Cloud TTS. Returns b'' for empty text."""
    if not text.strip():
        return b""

    from google.cloud import texttospeech

    language_code, voice_name = _VOICE_MAP.get(lang, _VOICE_MAP["he"])

    client = texttospeech.TextToSpeechClient()
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=0.92,
            pitch=0.0,
        ),
    )
    logger.debug("TTS synthesized %d chars → %d bytes", len(text), len(response.audio_content))
    return response.audio_content
