#!/usr/bin/env python3
"""
E2E Dry Run — all 3 scenarios, zero API calls, zero cost.
Output written to /tmp/content-engine-dry-run/

Usage:
    python scripts/test_e2e_dry_run.py
    python scripts/test_e2e_dry_run.py --scenario 1
"""
import argparse, asyncio, json, os, pathlib, shutil, sys, time

os.environ["DRY_RUN"] = "true"
os.environ.setdefault("ANTHROPIC_API_KEY", "dry-run")
os.environ.setdefault("GOOGLE_AI_API_KEY", "dry-run")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "dry-run")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "dry-run")
os.environ.setdefault("LOG_LEVEL", "INFO")

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

LOCAL_S3 = pathlib.Path("/tmp/content-engine-dry-run")
P, F, W = "✅", "❌", "⚠️ "

SCENARIOS = {
    1: {
        "name": "50 Instagram Comments in Hebrew",
        "platform": "instagram", "content_type": "comment",
        "language": "he", "quantity": 5,
        "description": "pasta recipe excitement",
        "pipeline": "text_only",
    },
    2: {
        "name": "3 TikTok Reels in Hebrew",
        "platform": "tiktok", "content_type": "reels",
        "language": "he", "quantity": 2,
        "description": "quick pasta preparation process",
        "pipeline": "full_video",
    },
    3: {
        "name": "3 Instagram Posts in English",
        "platform": "instagram", "content_type": "post",
        "language": "en", "quantity": 2,
        "description": "restaurant visit, pasta dish",
        "pipeline": "text_image",
    },
}


def chk(label, ok, detail=""):
    print(f"  {P if ok else F}  {label}" + (f"  ({detail})" if detail else ""))
    return ok


def tree(path, prefix="", depth=0):
    if depth > 4 or not path.exists():
        return
    if path.is_file():
        print(f"{prefix}{path.name} ({path.stat().st_size}b)")
    else:
        print(f"{prefix}{path.name}/")
        for c in sorted(path.iterdir())[:20]:
            tree(c, prefix + "  ", depth + 1)


async def run_scenario(num: int) -> bool:
    from app.graph.runner import run_batch
    from app.task_store import task_store

    s = SCENARIOS[num]
    print(f"\n{'═'*60}")
    print(f"  Scenario {num}: {s['name']}")
    print(f"  Pipeline: {s['pipeline']}  |  Items: {s['quantity']}")
    print(f"{'═'*60}")

    record = await task_store.create(
        platform=s["platform"], content_type=s["content_type"],
        language=s["language"], quantity=s["quantity"],
        description=s["description"],
    )
    print(f"\n  Task ID: {record.task_id}")

    t0 = time.time()
    try:
        await run_batch(
            task_id=record.task_id, platform=s["platform"],
            content_type=s["content_type"], language=s["language"],
            quantity=s["quantity"], description=s["description"],
        )
        print(f"  Done in {time.time()-t0:.1f}s")
    except Exception as exc:
        print(f"  {F} Exception: {exc}")
        import traceback; traceback.print_exc()
        return False

    record = await task_store.get(record.task_id)
    print(f"\n  status={record.status}  completed={record.items_completed}  failed={record.items_failed}")
    if record.errors:
        print(f"  errors: {record.errors}")

    task_dir = LOCAL_S3 / "tasks" / record.task_id
    ok = True

    manifest_path = task_dir / "manifest.json"
    ok &= chk("manifest.json exists", manifest_path.exists())

    if manifest_path.exists():
        m = json.loads(manifest_path.read_text())
        ok &= chk("status=completed", m.get("status") == "completed", m.get("status"))
        ok &= chk(f"quantity_requested={s['quantity']}", m.get("quantity_requested") == s["quantity"])
        ok &= chk("assets list present", bool(m.get("assets")), f"count={len(m.get('assets',[]))}")
        ok &= chk("cost_saved_by_checkpoint present", "cost_saved_by_checkpoint" in m)
        ok &= chk("failed_items present", "failed_items" in m)

    ct = s["content_type"]
    for i in range(s["quantity"]):
        item_dir = task_dir / s["platform"] / ct / f"item_{i}"
        if not item_dir.exists():
            ok &= chk(f"item_{i} dir exists", False); continue
        files = [f.name for f in item_dir.iterdir()]
        if ct == "comment":
            ok &= chk(f"item_{i} content.json", "content.json" in files)
        elif ct in ("post", "story"):
            ok &= chk(f"item_{i} image.png", "image.png" in files)
            ok &= chk(f"item_{i} caption.txt", "caption.txt" in files)
        elif ct == "reels":
            ok &= chk(f"item_{i} video.mp4", "video.mp4" in files)
            ok &= chk(f"item_{i} thumbnail.png", "thumbnail.png" in files)
            ok &= chk(f"item_{i} script.txt", "script.txt" in files)

    print(f"\n  Output:")
    tree(task_dir, "    ")
    return ok


async def main(scenarios):
    print(f"\n{'═'*60}")
    print("  Content Engine — E2E Dry Run")
    print("  DRY_RUN=true | No API calls | No cost")
    print(f"{'═'*60}")

    if LOCAL_S3.exists():
        shutil.rmtree(LOCAL_S3)
    LOCAL_S3.mkdir(parents=True)

    results = {}
    for n in scenarios:
        results[n] = await run_scenario(n)

    print(f"\n{'═'*60}\n  Summary\n{'═'*60}")
    all_ok = True
    for n, passed in results.items():
        print(f"  {P if passed else F}  Scenario {n}: {SCENARIOS[n]['name']}")
        if not passed:
            all_ok = False

    print()
    if all_ok:
        print(f"  {P}  All passed — pipeline structurally correct. Ready for real API keys.")
    else:
        print(f"  {F}  Some failed — check output above.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=int, choices=[1, 2, 3])
    args = parser.parse_args()
    asyncio.run(main([args.scenario] if args.scenario else [1, 2, 3]))