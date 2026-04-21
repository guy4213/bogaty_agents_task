"""בדיקה מקומית ל-Google Cloud TTS — מסנתז עברית ומנגן את הקובץ."""
import pathlib
import sys
import os

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.services.tts_service import synthesize

SAMPLES = [
    ("he", "הפסטה מוכנה והיא נראית מדהים — עשירה בטעמים עם עגבניות טריות ובזיליקום."),
    ("he", "זהו הרגע שבו הכל מתחבר יחד, וכל מרכיב תורם לתוצאה המושלמת."),
    ("en", "This is the moment everything comes together — rich tomato, fresh basil, and pasta cooked to perfection."),
]

out_dir = pathlib.Path("C:/tmp/tts_test")
out_dir.mkdir(parents=True, exist_ok=True)

for i, (lang, text) in enumerate(SAMPLES):
    print(f"\n[{i+1}] lang={lang}")
    print(f"     text: {text}")
    audio = synthesize(text, lang=lang)
    if not audio:
        print("     ❌ empty response")
        continue
    out_path = out_dir / f"sample_{i+1}_{lang}.mp3"
    out_path.write_bytes(audio)
    print(f"     ✅ {len(audio):,} bytes → {out_path}")

print(f"\nקבצים נשמרו ב: {out_dir}")
print("פתח אחד מהם כדי לשמוע את האיכות.")
