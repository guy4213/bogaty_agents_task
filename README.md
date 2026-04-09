# Content Engine — MVP

Autonomous multi-modal content generation system. Transforms text briefs into
platform-ready assets for Instagram, TikTok, Twitter/X, Telegram, and Facebook.

## Stack

- **API**: FastAPI (Python 3.12) + Uvicorn
- **Orchestration**: LangGraph 0.2+ with MemorySaver checkpointing
- **Text**: Claude API (Sonnet 4)
- **Images**: Nano Banana 2 via Gemini API (Gemini 3.1 Flash Image)
- **Video**: Veo 3.1 Full via Gemini API (with Video Extend)
- **Storage**: AWS S3 via boto3

## Setup

### 1. Clone and configure

```bash
git clone <repo>
cd content-engine
cp .env.example .env
# Fill in your API keys in .env
```

### 2. Run with Docker (recommended)

```bash
docker compose up --build
```

The API is available at `http://localhost:8000`.
OpenAPI docs at `http://localhost:8000/docs`.

### 3. Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate` | Submit a content generation task |
| GET | `/tasks/{task_id}` | Poll task status and results |
| GET | `/tasks` | List all tasks (dev use) |
| GET | `/health` | Service health + circuit breaker states |
| GET | `/` | Liveness probe |

## Test Scenarios

### Scenario 1 — 50 Instagram Comments in Hebrew

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "instagram",
    "content_type": "comment",
    "language": "he",
    "quantity": 50,
    "description": "pasta recipe excitement"
  }'
```

Expected: ~1-2 min, ~$0.08-0.12. Single Claude API call for all 50 comments.
S3 output: `tasks/{id}/instagram/comment/item_0/content.json`

---

### Scenario 2 — 3 TikTok Reels in Hebrew

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "tiktok",
    "content_type": "reels",
    "language": "he",
    "quantity": 3,
    "description": "quick pasta preparation process"
  }'
```

Expected: ~8-12 min, ~$3-5. Each Reel: 1 initial Veo clip + 3 Extend calls.
S3 output: `tasks/{id}/tiktok/reels/item_{0-2}/` (video.mp4, thumbnail.png, script.txt)

---

### Scenario 3 — 3 Instagram Post Images in English

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "instagram",
    "content_type": "post",
    "language": "en",
    "quantity": 3,
    "description": "restaurant visit, pasta dish"
  }'
```

Expected: ~2-4 min, ~$0.15-0.25. Images 2+3 use Style Reference from image 1.
S3 output: `tasks/{id}/instagram/post/item_{0-2}/` (image.png, caption.txt)

---

### Poll for results

```bash
curl http://localhost:8000/tasks/{task_id}
```

### Check service health

```bash
curl http://localhost:8000/health
```

## Architecture

```
POST /generate
    └── run_batch()                    [Tier 1: per-item try/except]
            └── graph.ainvoke()        [Tier 2: LangGraph MemorySaver]
                    ├── orchestrator   sets pipeline_type
                    ├── content_agent  Claude — single-call batch
                    ├── image_agent    Nano Banana 2 + Style Reference
                    ├── video_agent    Veo 3.1 + Extend loop [Tier 3]
                    └── content_validator  langdetect + Jaccard + Claude LLM gate
```

### Three-tier checkpointing

- **Tier 1 (batch)**: each item runs in its own `try/except`. One failure doesn't abort the batch. Successful items upload to S3 immediately.
- **Tier 2 (pipeline)**: LangGraph MemorySaver snapshots state after each node. Retry with the same `thread_id` resumes from the last completed node.
- **Tier 3 (node)**: Video Agent saves `current_video_ref` + `completed_extends` into state after every Extend call. Retry resumes the Extend loop from the last successful iteration.

### S3 structure

```
content-engine-prod/
  tasks/{task_id}/
    manifest.json
    {platform}/{content_type}/
      item_0/
        content.json   (text / captions)
        image.png      (posts / stories)
        thumbnail.png  (reels)
        video.mp4      (reels)
        script.txt     (reels)
        caption.txt
```

### manifest.json fields

```json
{
  "task_id": "...",
  "status": "completed | partial | failed",
  "quantity_requested": 3,
  "quantity_delivered": 3,
  "quantity_failed": 0,
  "total_cost_usd": 4.20,
  "cost_saved_by_checkpoint": 0.55,
  "failed_items": [],
  "assets": [...]
}
```

## Post-MVP

To migrate to production infrastructure, uncomment in `docker-compose.yml`:
- `worker` (Celery)
- `redis`
- `postgres`
- `prometheus` + `grafana`

Swap `MemorySaver` → `PostgresSaver` in `app/graph/graph.py` (one line change).
Swap in-memory `task_store` → repository backed by PostgreSQL (repository pattern already in place).