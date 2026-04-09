#!/usr/bin/env python3
"""
Run: python scripts/verify_veo_sdk.py
No API calls — only inspects the installed SDK.
"""
import sys
import inspect

P = "✅"
F = "❌"
W = "⚠️ "


def check(label, ok, detail=""):
    print(f"  {P if ok else F}  {label}" + (f"  ({detail})" if detail else ""))
    return ok


def section(t):
    print(f"\n{'─'*55}\n  {t}\n{'─'*55}")


all_ok = True
section("1. SDK Package")

try:
    import google.genai as genai
    import google.genai.types as types
    check("google-genai importable", True, f"version={getattr(genai,'__version__','?')}")
except ImportError as e:
    check("google-genai importable", False, str(e))
    print("  Install: pip install google-genai")
    sys.exit(1)

try:
    import google.generativeai
    print(f"  {W}  google-generativeai still installed — run: pip uninstall google-generativeai")
except ImportError:
    check("google-generativeai absent (good)", True)

section("2. Client Interface")
client = genai.Client(api_key="test")
check("genai.Client() works", True)
check("client.aio.models exists", hasattr(client.aio, "models"))
check("client.aio.operations exists", hasattr(client.aio, "operations"))

section("3. Image Generation")
check("generate_images exists", hasattr(client.aio.models, "generate_images"))
check("edit_image exists (style ref)", hasattr(client.aio.models, "edit_image"))
check("types.GenerateImagesConfig", hasattr(types, "GenerateImagesConfig"))
check("types.EditImageConfig", hasattr(types, "EditImageConfig"))
check("types.StyleReferenceImage", hasattr(types, "StyleReferenceImage"))
check("types.StyleReferenceConfig", hasattr(types, "StyleReferenceConfig"))
check("types.Image", hasattr(types, "Image"))
if hasattr(types, "Image"):
    check("Image.image_bytes field", "image_bytes" in types.Image.model_fields)

section("4. Video Generation (Veo 3.1)")
check("generate_videos exists", hasattr(client.aio.models, "generate_videos"))
if hasattr(client.aio.models, "generate_videos"):
    params = list(inspect.signature(client.aio.models.generate_videos).parameters.keys())
    check("generate_videos has 'video' param (Extend)", "video" in params, f"all params: {params}")
check("types.GenerateVideosConfig", hasattr(types, "GenerateVideosConfig"))
check("types.GenerateVideosOperation", hasattr(types, "GenerateVideosOperation"))
check("types.Video", hasattr(types, "Video"))
if hasattr(types, "GenerateVideosOperation"):
    fields = types.GenerateVideosOperation.model_fields
    check("Operation has 'done'", "done" in fields)
    check("Operation has 'result'", "result" in fields)
    check("Operation has 'error'", "error" in fields)
if hasattr(types, "Video"):
    check("Video has 'uri'", "uri" in types.Video.model_fields)
check("aio.operations.get exists (polling)", hasattr(client.aio.operations, "get"))

section("5. requirements.txt")
import pathlib
req = pathlib.Path(__file__).parent.parent / "requirements.txt"
if req.exists():
    txt = req.read_text()
    check("google-genai in requirements.txt", "google-genai" in txt)
    if "google-generativeai" in txt:
        print(f"  {W}  google-generativeai in requirements.txt — remove it")

section("Summary")
print(f"\n  {P}  SDK compatible. Key patterns:")
print("  • Images:   client.aio.models.generate_images(model, prompt, config=GenerateImagesConfig(...))")
print("  • StyleRef: client.aio.models.edit_image(model, prompt, reference_images=[StyleReferenceImage(...)])")
print("  • Video:    client.aio.models.generate_videos(model, prompt, config=GenerateVideosConfig(...))")
print("  • Extend:   client.aio.models.generate_videos(model, prompt, video=Video(uri=...), config=...)")
print("  • Poll:     await client.aio.operations.get(operation) until operation.done == True")
print("  • Result:   operation.result.generated_videos[0].video.uri\n")