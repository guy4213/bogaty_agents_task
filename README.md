# Content Engine

> Autonomous multi-modal content generation system.  
> Send a text brief → get platform-ready assets for Instagram, TikTok, Twitter/X, Telegram, and Facebook.

---

## What This System Does

Content Engine is a multi-agent pipeline that takes a short description (e.g. *"quick pasta recipe"*) and autonomously produces:

- **Comments** — batches of up to 200 unique, persona-varied comments in a single API call
- **Posts** — caption + image with platform-correct dimensions and Style Reference consistency across a batch
- **Stories** — same as posts but in 9:16 vertical format
- **Reels** — full video (15s or 30s, configurable) with AI-generated music, Hebrew/English TTS narration, burned-in captions, and a matching thumbnail

Supports **Hebrew and English** natively across all content types, with full RTL support.

---

## How It Works

Each request is routed through a deterministic LangGraph pipeline based on content type:

```
comment  →  Content Agent → Validator
post     →  Content Agent → Image Agent → Validator
story    →  Content Agent → Image Agent → Validator
reels    →  Content Agent → Style Reference (Imagen) → Video Agent → Validator
```

### Agents

| Agent | Model | Responsibility |
|---|---|---|
| **Content Agent** | Claude Sonnet 4.5 | Generates full batches as a single structured JSON response. Includes persona rotation for comments, scene scripts for reels. Accepts retry feedback from the Validator. |
| **Image Agent** | Gemini Imagen 4 | Generates platform-sized images (1:1, 9:16). First image anchors a Style Reference used for visual consistency across the batch. |
| **Video Agent** | Kling 2.6 (T2V) + Kling v2.1 Pro (I2V) via kie.ai | Generates clip 1 (T2V with AI music), then extends via image-to-video from each clip's last frame. FFmpeg merges clips, loops music from clip 1 across full duration, mixes Google Cloud TTS narration, and burns captions. |
| **Content Validator** | Claude + langdetect | Two-layer: deterministic checks (language, length, Jaccard similarity ≥ 0.7) + LLM quality score (1–10, reject < 6). Feeds retry feedback back to the Content Agent, up to 2 retries. |

### Video Pipeline Detail

For a 3-scene reel (default 10s per clip = 30s total):

```
Scene 1  →  Kling 2.6 T2V  (10s, with AI music, sound=true)
Scene 2  →  Kling v2.1 Pro I2V  (10s, image-to-video from Scene 1 last frame)
Scene 3  →  Kling v2.1 Pro I2V  (10s, image-to-video from Scene 2 last frame, payoff)
         ↓
FFmpeg:  concat 3 clips + loop Scene 1 music to 30s
         + Google Cloud TTS narration mixed at 25% music / 75% voice
         + captions burned in (Hebrew RTL or English)
         ↓
S3:  video.mp4 + script.txt + manifest.json
```

Clip duration is controlled by a single env var (`KIE_CLIP_DURATION=5` or `10`).

### Checkpointing (3 tiers)

The system is designed to **never re-run a step it already completed**:

1. **Batch level** — each item runs independently. One failure doesn't cancel others.
2. **Pipeline level** — LangGraph `MemorySaver` with unique `thread_id` per item. Retrying a failed task resumes from the last succeeded node.
3. **Node level** — the Video Agent saves `completed_extends` after each clip. A crash at clip 2 of 3 resumes from clip 3.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Server | FastAPI (Python 3.12) + Uvicorn |
| Frontend | Next.js 14 (App Router) + React Query |
| Agent Orchestration | LangGraph 1.x with MemorySaver |
| Text Generation | Anthropic Claude Sonnet 4.5 |
| Image Generation | Gemini Imagen 4 via Google AI API |
| Video Generation | Kling 2.6 / v2.1 Pro via kie.ai |
| TTS | Google Cloud Text-to-Speech (Wavenet) |
| Cloud Storage | AWS S3 via boto3 |
| Media Processing | FFmpeg via `static-ffmpeg` (clip merge, audio mix, caption burn) |
| Observability | LangSmith (optional) |
| Containerisation | Docker + docker-compose |

---

## Prerequisites

Accounts and credentials needed:

- **Anthropic** — API key for Claude
- **Google AI** — API key for Imagen image generation
- **Google Cloud** — project with Cloud Text-to-Speech API enabled + service account credentials
- **kie.ai** — account with credits for Kling video generation
- **AWS** — S3 bucket + IAM credentials

---

## Cloud Setup

### 1. Anthropic

1. Go to [console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key.
2. Copy the key → `ANTHROPIC_API_KEY`.

---

### 2. Google AI (Imagen — Images)

1. Go to [aistudio.google.com](https://aistudio.google.com) → Get API Key.
2. Copy the key → `GOOGLE_AI_API_KEY`.
3. Make sure the **Generative Language API** is enabled on your project.

---

### 3. Google Cloud (TTS — Voice Narration)

TTS requires a service account with the Cloud Text-to-Speech API enabled.

```bash
# Enable the API
gcloud services enable texttospeech.googleapis.com

# Create service account
gcloud iam service-accounts create content-engine \
  --display-name="Content Engine"

# Grant TTS role
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:content-engine@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudtexttospeech.user"

# Download credentials
gcloud iam service-accounts keys create credentials.json \
  --iam-account=content-engine@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

Set `GOOGLE_APPLICATION_CREDENTIALS` to the path of `credentials.json`.

---

### 4. kie.ai (Kling Video Generation)

1. Sign up at [kie.ai](https://kie.ai) and top up credits.
2. Go to your dashboard → API Keys → Create Key.
3. Copy the key → `KIE_API_KEY`.

**Cost per video:** ~$0.55 per 10s clip × 3 clips = ~$1.65–2.70 per reel (varies by model).

---

### 5. AWS S3 (Asset Storage)

```bash
# Create bucket (replace region with your preferred region)
aws s3api create-bucket \
  --bucket your-content-engine-bucket \
  --region eu-north-1 \
  --create-bucket-configuration LocationConstraint=eu-north-1

# Create IAM user
aws iam create-user --user-name content-engine

# Attach S3 policy
aws iam attach-user-policy \
  --user-name content-engine \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

# Generate access keys
aws iam create-access-key --user-name content-engine
```

Copy `AccessKeyId` → `AWS_ACCESS_KEY_ID` and `SecretAccessKey` → `AWS_SECRET_ACCESS_KEY`.

---

### 6. LangSmith (Optional — Tracing)

1. Go to [smith.langchain.com](https://smith.langchain.com) → Settings → API Keys.
2. Copy the key → `LANGSMITH_API_KEY`.
3. Set `LANGSMITH_TRACING=true` in `.env` to enable.

---

## Local Setup

### 1. Clone and configure

```bash
git clone <repo>
cd content-engine
cp .env.example .env
# Edit .env with your keys
```

### 2. Run backend with Docker (recommended)

```bash
docker compose up --build
```

API at `http://localhost:8000` · Docs at `http://localhost:8000/docs`

### 3. Run backend locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend at `http://localhost:3000`

### 5. Dry-run mode (no API calls, no cost)

```bash
DRY_RUN=true uvicorn app.main:app --reload
```

Runs the full pipeline with mock responses — useful for testing pipeline structure and S3 output format.

---

## Environment Variables

```bash
# ── Anthropic ──────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-5

# ── Google AI (images) ─────────────────────────────────────
GOOGLE_AI_API_KEY=AIza...

# ── Google Cloud (TTS voice narration) ─────────────────────
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json

# ── kie.ai / Kling (video generation) ──────────────────────
KIE_API_KEY=...
KIE_API_BASE=https://api.kie.ai               # default
KIE_MODEL_T2V=kling-2.6/text-to-video        # text-to-video (clip 1)
KIE_MODEL_I2V=kling/v2-1-pro                  # image-to-video (clips 2-3)
KIE_CLIP_DURATION=10                          # 5 or 10 seconds per clip
VIDEO_PROVIDER=kling

# ── AWS S3 (asset storage) ─────────────────────────────────
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=your-content-engine-bucket
S3_REGION=eu-north-1

# ── Image model config ─────────────────────────────────────
IMAGE_MODEL_FIRST=imagen-4.0-fast-generate-001
IMAGE_MODEL_STYLE_REF=gemini-3.1-flash-image-preview

# ── Validation & retry ─────────────────────────────────────
CONTENT_VALIDATOR_MIN_SCORE=6               # reject if Claude scores < 6
MAX_RETRIES_PER_ITEM=2
JACCARD_SIMILARITY_THRESHOLD=0.7            # batch uniqueness threshold

# ── Circuit breakers ───────────────────────────────────────
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_WINDOW_SEC=120
CIRCUIT_BREAKER_RECOVERY_SEC=60

# ── LangSmith tracing (optional) ───────────────────────────
LANGSMITH_API_KEY=ls__...
LANGSMITH_TRACING=false

# ── Dev ────────────────────────────────────────────────────
DRY_RUN=false
LOG_LEVEL=INFO
```

> **Video duration:** `KIE_CLIP_DURATION=5` → 15s video (~$1.35), `KIE_CLIP_DURATION=10` → 30s video (~$2.70). Only `5` and `10` are valid values.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/generate` | Submit a content generation task (async) |
| `GET` | `/tasks/{task_id}` | Poll task status and results |
| `GET` | `/tasks/{task_id}/content` | Get generated assets with download URLs |
| `GET` | `/tasks` | List all tasks |
| `GET` | `/health` | Service health + circuit breaker states |
| `GET` | `/` | Liveness probe |

---

## Usage Examples

### Scenario 1 — 50 Instagram Comments (Hebrew)

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

All 50 comments generated in **one Claude call** with persona rotation.  
Expected: ~1–2 min · ~$0.05–0.10

---

### Scenario 2 — 1 TikTok Reel (Hebrew, 30s)

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "tiktok",
    "content_type": "reels",
    "language": "he",
    "quantity": 1,
    "description": "motivational video for athletes"
  }'
```

3 Kling clips (10s each) → merged → AI music looped → Hebrew TTS voice → captions burned.  
Expected: ~5–7 min · ~$2.70  
S3: `videos/{task_id}/tiktok/item_0/` — `video.mp4`, `script.txt`

---

### Scenario 3 — 3 Instagram Posts (English)

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

Images 2 and 3 use Style Reference from image 1 for visual consistency.  
Expected: ~2–4 min · ~$0.15–0.25

---

### Polling for results

```bash
# Status
curl http://localhost:8000/tasks/{task_id}

# Full content with download URLs
curl http://localhost:8000/tasks/{task_id}/content
```

```json
{
  "task_id": "abc-123",
  "status": "completed",
  "quantity_delivered": 1,
  "total_cost_usd": 2.72,
  "assets": [
    { "asset_type": "video", "download_url": "https://s3.amazonaws.com/..." },
    { "asset_type": "text",  "content": { "scenes": [...] } }
  ]
}
```

Statuses: `pending` → `processing` → `completed` / `partial` / `failed`

---

## S3 Output Structure

```
videos/{task_id}/
  manifest.json                    ← full task summary + cost breakdown
  {platform}/
    item_0/
      video.mp4                    ← final merged video (reels)
      script.txt                   ← scene-by-scene script
      content.json                 ← captions, hashtags, narrator text
      thumbnail.png                ← style reference image

posts/{task_id}/
  manifest.json
  {platform}/
    item_0/
      image.png
      content.json

comments/{task_id}/
  manifest.json
  {platform}/
    item_0/
      content.json                 ← all comments as JSON array
```

`manifest.json` includes: `quantity_requested`, `quantity_delivered`, `failed_items` (with reasons), `total_cost_usd`, and `cost_saved_by_checkpoint`.

---

## Health Check

```bash
curl http://localhost:8000/health
```

```json
{
  "overall": "healthy",
  "services": [
    { "service": "claude",  "status": "healthy", "latency_ms": 312, "circuit_state": "closed" },
    { "service": "gemini",  "status": "healthy", "latency_ms": 180, "circuit_state": "closed" },
    { "service": "s3",      "status": "healthy", "latency_ms": 45,  "circuit_state": "closed" },
    { "service": "kling",   "status": "healthy", "latency_ms": 210, "circuit_state": "closed" }
  ],
  "timestamp": "2026-04-27T10:00:00Z"
}
```

Each service has a circuit breaker: trips after 5 consecutive failures within 120s, recovers after 60s.

---

## Limits

| Content Type | Max Quantity |
|---|---|
| comment | 200 |
| post | 50 |
| story | 50 |
| reels | 50 |

Submit multiple requests for larger batches.
