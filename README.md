# Content Engine

> Autonomous multi-modal content generation system.  
> Send a text brief → get platform-ready assets for Instagram, TikTok, Twitter/X, Telegram, and Facebook.

---

## What This System Does

Content Engine is a multi-agent pipeline that takes a short description (e.g. *"quick pasta recipe"*) and autonomously produces:

- **Comments** — batches of up to 50 unique, persona-varied comments in a single API call
- **Posts** — caption + image with platform-correct dimensions and Style Reference consistency across a batch
- **Stories** — same as posts but in 9:16 vertical format
- **Reels** — full video (≈29s) with embedded captions, native audio, and a matching thumbnail

Supports **Hebrew and English** natively across all content types.

---

## How It Works

Each request is routed through a deterministic LangGraph pipeline based on content type:

```
comment  →  Content Agent → Validator
post     →  Content Agent → Image Agent → Validator
story    →  Content Agent → Image Agent → Validator
reels    →  Content Agent → Image Agent (thumbnail) → Video Agent → Validator
```

### Agents

| Agent | Model | Responsibility |
|---|---|---|
| **Content Agent** | Claude Sonnet 4 | Research + copywriting in one call. Generates full batches (e.g. 50 comments) as a single structured JSON response. Includes persona rotation for variety. |
| **Image Agent** | Nano Banana 2 (Gemini 3.1 Flash Image) | Generates platform-sized images natively (1:1, 9:16). Uses Style Reference — first image anchors the visual style for all subsequent images in the batch. |
| **Video Agent** | Veo 3.1 Full (Vertex AI) | Generates an 8s clip then extends it in 7s increments. Audio is native to Veo. Payoff scene uses image-to-video for visual accuracy; FFmpeg crossfades audio at the join. Hebrew captions are burned in via FFmpeg. |
| **Content Validator** | Claude + langdetect | Two-layer validation: deterministic checks (language, length, uniqueness via Jaccard similarity) + LLM quality score (1–10, reject if < 6). Feeds retry feedback back to the originating agent, up to 2 retries. |

### Checkpointing (3 tiers)

The system is designed to **never re-run a step it already completed**, protecting against wasted API spend:

1. **Batch level** — each item runs in its own `try/except`. One failure doesn't cancel the rest. Completed items upload to S3 immediately.
2. **Pipeline level** — LangGraph `MemorySaver` gives each item a unique `thread_id`. Retrying a failed video task skips the Content and Image nodes that already succeeded.
3. **Node level** — the Video Agent saves `completed_extends` to state after each Veo Extend call. A crash at extend 3 of 4 resumes from extend 4, not from scratch.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Server | FastAPI (Python 3.12) + Uvicorn |
| Agent Orchestration | LangGraph 1.x with MemorySaver |
| Text Generation | Anthropic Claude Sonnet 4 |
| Image Generation | Google Nano Banana 2 via Gemini API |
| Video Generation | Google Veo 3.1 Full via Vertex AI |
| Cloud Storage (assets) | AWS S3 via boto3 |
| Cloud Storage (Veo temp) | Google Cloud Storage (GCS) |
| Media Processing | FFmpeg via `static-ffmpeg` (clip merge + caption burn) |
| Observability | LangSmith (optional) |
| Containerisation | Docker + docker-compose |

---

## Prerequisites

Before setup, you need accounts and credentials for:

- **Anthropic** — API key for Claude
- **Google Cloud** — project with Vertex AI + GCS enabled (for Veo)
- **Google AI Studio** — API key for Nano Banana 2 image generation
- **AWS** — S3 bucket + IAM credentials

---

## Cloud Setup

### 1. Anthropic

1. Go to [console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key.
2. Copy the key — you'll need it as `ANTHROPIC_API_KEY`.

---

### 2. Google AI Studio (Nano Banana 2 — Images)

1. Go to [aistudio.google.com](https://aistudio.google.com) → Get API Key.
2. Copy the key — you'll need it as `GOOGLE_AI_API_KEY`.
3. Make sure your project has the **Generative Language API** enabled.

---

### 3. Google Cloud (Vertex AI — Veo Video Generation)

Veo 3.1 runs on Vertex AI and requires a separate GCP project setup.

#### 3a. Create / select a GCP project

```bash
gcloud projects create YOUR_PROJECT_ID   # or use an existing one
gcloud config set project YOUR_PROJECT_ID
```

#### 3b. Enable required APIs

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  storage.googleapis.com
```

#### 3c. Request Veo 3.1 access

Veo 3.1 is an allowlisted model. Request access at:  
[cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos](https://cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos)

> ⚠️ Without allowlist approval, Veo API calls will return a 403. This can take 1–2 business days.

#### 3d. Create a GCS bucket for Veo temp storage

Veo returns videos to GCS. Create a bucket in the same region as your Vertex location (`us-central1` by default):

```bash
gsutil mb -l us-central1 gs://YOUR_PROJECT_ID-veo-temp
```

Set this as `GCS_BUCKET_NAME` in your `.env`.

#### 3e. Create a service account

```bash
# Create service account
gcloud iam service-accounts create content-engine \
  --display-name="Content Engine"

# Grant required roles
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:content-engine@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:content-engine@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Download credentials JSON
gcloud iam service-accounts keys create credentials.json \
  --iam-account=content-engine@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

Place `credentials.json` in the project root and set `GOOGLE_APPLICATION_CREDENTIALS=credentials.json` in your `.env`.

---

### 4. AWS S3 (Asset Storage)

#### 4a. Create an S3 bucket

```bash
aws s3api create-bucket \
  --bucket content-engine-prod \
  --region eu-west-1 \
  --create-bucket-configuration LocationConstraint=eu-west-1
```

#### 4b. Create an IAM user with S3 access

```bash
# Create user
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

### 5. LangSmith (Optional — Tracing)

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
# Edit .env with your keys (see Environment Variables section below)
```

### 2. Run with Docker (recommended)

```bash
docker compose up --build
```

API available at `http://localhost:8000`  
OpenAPI docs at `http://localhost:8000/docs`

### 3. Run locally without Docker

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Dry-run mode (no real API calls)

Set `DRY_RUN=true` in `.env` to run the full pipeline using mock responses. Useful for testing the pipeline structure, checkpointing, and S3 output format without spending API credits.

```bash
DRY_RUN=true uvicorn app.main:app --reload
```

---

## Environment Variables

Create a `.env` file in the project root. All variables below:

```bash
# ── Anthropic ──────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-5              # default

# ── Google AI Studio (images) ──────────────────────────────
GOOGLE_AI_API_KEY=AIza...

# ── Google Cloud / Vertex AI (video) ───────────────────────
VERTEX_PROJECT_ID=your-gcp-project-id
VERTEX_LOCATION=us-central1                 # default
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
GCS_BUCKET_NAME=your-project-veo-temp       # GCS bucket for Veo output

# ── AWS S3 (asset storage) ─────────────────────────────────
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=content-engine-prod          # default
S3_REGION=eu-west-1                         # default

# ── LangSmith tracing (optional) ───────────────────────────
LANGSMITH_API_KEY=ls__...
LANGSMITH_TRACING=false                     # set to true to enable

# ── Model config ───────────────────────────────────────────
VEO_MODEL=veo-3.1-generate-preview
VEO_TIMEOUT_SEC=90
VEO_INITIAL_DURATION_SEC=8
VEO_EXTEND_DURATION_SEC=7
VEO_TARGET_DURATION_SEC=29

IMAGE_MODEL_FIRST=imagen-4.0-fast-generate-001
IMAGE_MODEL_STYLE_REF=gemini-3.1-flash-image-preview

# ── Validation & retry ─────────────────────────────────────
CONTENT_VALIDATOR_MIN_SCORE=6               # reject if Claude scores < 6
MAX_RETRIES_PER_ITEM=2
JACCARD_SIMILARITY_THRESHOLD=0.7            # batch uniqueness threshold

# ── Circuit breakers ───────────────────────────────────────
CIRCUIT_BREAKER_THRESHOLD=5                 # consecutive failures to trip
CIRCUIT_BREAKER_WINDOW_SEC=120
CIRCUIT_BREAKER_RECOVERY_SEC=60

# ── Dev ────────────────────────────────────────────────────
DRY_RUN=false
LOG_LEVEL=INFO
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/generate` | Submit a content generation task (async) |
| `GET` | `/tasks/{task_id}` | Poll task status and results |
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

All 50 comments are generated in **one Claude API call** with persona rotation.  
Expected: ~1–2 min · ~$0.08–0.12  
S3: `tasks/{id}/instagram/comment/item_0/content.json`

---

### Scenario 2 — 3 TikTok Reels (Hebrew)

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

Each Reel: 1 initial Veo clip (8s) + 3 Extend calls (7s each) = ≈29s.  
Hebrew captions burned in via FFmpeg. Audio crossfaded at the payoff scene join.  
Expected: ~8–12 min · ~$3–5  
S3: `tasks/{id}/tiktok/reels/item_{0-2}/` — `video.mp4`, `thumbnail.png`, `script.txt`

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
S3: `tasks/{id}/instagram/post/item_{0-2}/` — `image.png`, `caption.txt`, `metadata.json`

---

### Polling for results

```bash
curl http://localhost:8000/tasks/{task_id}
```

```json
{
  "task_id": "abc123",
  "status": "completed",
  "items_completed": 3,
  "items_failed": 0,
  "total_cost_usd": 0.21,
  "s3_manifest_url": "https://..."
}
```

Possible statuses: `pending` → `processing` → `completed` / `partial` / `failed`

---

## S3 Output Structure

```
tasks/{task_id}/
  manifest.json                         ← summary of the full task
  {platform}/{content_type}/
    item_0/
      content.json / image.png / video.mp4
      caption.txt
      metadata.json
    item_1/
      ...
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
    { "service": "claude", "status": "up", "circuit_state": "closed" },
    { "service": "gemini", "status": "up", "circuit_state": "closed" },
    { "service": "s3",     "status": "up", "circuit_state": "closed" }
  ],
  "timestamp": "2026-04-15T10:00:00Z"
}
```

Each service has a circuit breaker: trips after 5 consecutive failures within 120s, recovers via a single probe request every 60s.