# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
python -m venv .venv && pip install -r requirements.txt

# Run dev server (live reload)
uvicorn app.main:app --reload --port 8000

# Run in dry-run mode (no API calls, no cost)
DRY_RUN=true uvicorn app.main:app --reload

# E2E dry-run test (all 3 scenarios)
python app/scripts/test_e2e_dry_run.py

# Single scenario (1=comment, 2=post/story, 3=reels)
python app/scripts/test_e2e_dry_run.py --scenario 1

# Frontend
cd frontend && npm install && npm run dev

# Docker
docker compose up --build
```

Required env vars: `ANTHROPIC_API_KEY`, `GOOGLE_AI_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`, `KIE_API_KEY`.
Optional: `LANGSMITH_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS` (for TTS).

## Architecture

**Purpose**: Converts text briefs into platform-ready multi-modal content (comments, posts, stories, reels) for Instagram, TikTok, Twitter/X, Telegram, Facebook — in Hebrew and English.

### Pipeline routing

```
content_type → pipeline_type → agent chain
comment      → text_only     → orchestrator → content_agent → validator
post/story   → text_image    → orchestrator → content_agent → image_agent → validator
reels        → full_video    → orchestrator → content_agent → style_ref (imagen) → video_agent → validator
```

The LangGraph `StateGraph` in `graph/graph.py` wires these nodes with conditional edges. `ContentEngineState` (TypedDict in `graph/state.py`) carries all pipeline context, outputs, and cost tracking.

### Batch execution (`graph/runner.py`)

`run_batch()` is the top-level entry point called by the `/generate` endpoint:
1. Generates a single **style reference image** upfront (visual consistency for the whole batch)
2. Launches all items **in parallel** under global semaphores (`text_only`=48, `text_image`=18, `full_video`=8)
3. Each item runs its own LangGraph thread with a unique `thread_id` for independent checkpoint/retry
4. Writes S3 manifest on completion

### Three-tier checkpointing

- **Batch level**: Each item is independent; one failure doesn't cancel others
- **Pipeline level**: LangGraph `MemorySaver` + `thread_id` — resubmitting a failed item resumes from the last succeeded node
- **Node level** (video only): `completed_extends` + `all_video_refs` saved after each Kling clip — partial video completions survive crashes

### Agents

| Agent | Model | Notes |
|---|---|---|
| `agents/content_agent.py` | Claude Sonnet 4.5 | Generates full batches (captions, personas, hashtags, scene scripts). Accepts retry feedback from validator. Kling prompt uses `KIE_CLIP_DURATION` for scene duration. |
| `agents/image_agent.py` | Gemini Imagen 4 | Platform-sized images (1:1 or 9:16). First image is the style reference for the batch. |
| `agents/video_agent.py` | Kling 2.6 (T2V) + Kling v2.1 Pro (I2V) via kie.ai | 3 clips × `KIE_CLIP_DURATION` seconds. FFmpeg merges clips, loops clip-1 music via `-stream_loop -1`, mixes Google Cloud TTS voice, burns captions. |
| `agents/content_validator.py` | Claude + langdetect | Two-layer: deterministic (language, length, Jaccard ≥0.7) + LLM score (reject <6/10). Max 2 retries per item. |
| `agents/orchestrator.py` | — | Pure routing: `content_type` → `pipeline_type` |

### Services & QA

- `services/claude_client.py` — Anthropic API with tenacity retry + circuit breaker
- `services/gemini_client.py` — Imagen generation + style reference
- `services/kie_client.py` — Kling T2V + I2V via kie.ai, polls `/api/v1/jobs/recordInfo`
- `services/tts_service.py` — Google Cloud TTS Wavenet (he-IL-Wavenet-B / en-US-Wavenet-D)
- `services/s3_client.py` — async boto3; dry-run mock support
- `services/caption_service.py` — FFmpeg clip merge, audio loop, TTS mix, caption burn
- `qa/circuit_breaker.py` — per-service breaker (5 failures in 120s → open; 60s recovery)
- `qa/health_checks.py` — pre-flight pings for Claude, Gemini, S3, Kling
- `mocks/mock_clients.py` — fake responses for `DRY_RUN=true`

### Key limits (from `config.py`)

- Max quantities: comments=200, posts/stories/reels=50
- Validation thresholds: LLM score <6 = reject; Jaccard similarity >0.7 = duplicate
- Circuit breaker: 5 failures / 120s window → open; 60s half-open recovery
- Clip duration: `KIE_CLIP_DURATION=5` (15s video, ~$1.35) or `10` (30s video, ~$2.70)

### Task lifecycle

Tasks are tracked in `task_store.py` (in-memory `asyncio.Lock`-protected dict). Statuses: `pending → processing → completed/partial/failed`. Swap for a DB post-MVP.

### API endpoints (`main.py`)

- `POST /generate` — create task, start `run_batch` in background
- `GET /tasks/{task_id}` — status + results
- `GET /tasks/{task_id}/content` — assets with presigned S3 download URLs
- `GET /tasks` — list all (dev)
- `GET /health` — service health + circuit breaker state
- `GET /` — liveness

## Rules
- Don't explain what you're about to do, just do it
- Don't summarize what you did after finishing
- Ask clarifying questions before writing code
- When editing code, show only the changed parts
- Think step by step before implementing anything complex
