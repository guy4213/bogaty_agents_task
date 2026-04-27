# Content Engine — Production Architecture & Design Document
## Autonomous Multi-Modal Content Generation System

**Author:** Guy Franses
**Date:** April 2026
**Version:** 5.0 — Kling Migration

---

## 1. Executive Summary

Content Engine הוא מערכת אוטונומית לייצור תוכן מולטי-מודאלי. המערכת מקבלת brief טקסטואלי קצר ומייצרת assets מוכנים לפרסום עבור Instagram, TikTok, Twitter/X, Telegram ו-Facebook — בעברית ואנגלית.

גרסה 5.0 מחליפה את Veo (Vertex AI) ב-Kling (kie.ai) לייצור וידאו, ומוסיפה:
- מוזיקה AI-generated נטיבית בקליפים
- TTS (Google Cloud Wavenet) לנרטיב דובר בכל סצנה
- שליטה מלאה על משך הקליפ דרך משתנה סביבה אחד
- תיקוני QA מקיפים בפרונטאנד

---

## 2. ארכיטקטורת המערכת

### 2.1 Pipeline Routing

```
content_type  →  pipeline_type  →  agent chain
─────────────────────────────────────────────────────────────
comment       →  text_only      →  Orchestrator → Content Agent → Validator
post/story    →  text_image     →  Orchestrator → Content Agent → Image Agent → Validator
reels         →  full_video     →  Orchestrator → Content Agent → Style Ref (Imagen) → Video Agent → Validator
```

### 2.2 Stack טכנולוגי

| שכבה | טכנולוגיה |
|---|---|
| API Server | FastAPI (Python 3.12) + Uvicorn |
| Frontend | Next.js 14 (App Router) + TanStack Query v5 |
| Agent Orchestration | LangGraph 1.x + MemorySaver |
| Text Generation | Claude Sonnet 4.5 (Anthropic) |
| Image Generation | Gemini Imagen 4 via Google AI API |
| Video Generation | Kling 2.6 (T2V) + Kling v2.1 Pro (I2V) via kie.ai |
| Voice Narration | Google Cloud TTS — Wavenet (he-IL-Wavenet-B / en-US-Wavenet-D) |
| Asset Storage | AWS S3 via boto3 |
| Media Processing | FFmpeg via static-ffmpeg (merge, audio loop, TTS mix, caption burn) |
| Observability | LangSmith (optional) + structured logging |
| Containerisation | Docker + docker-compose |

---

## 3. Agent Definitions

### Agent 1 — Orchestrator
- מנתח פרמטרים וקובע pipeline_type
- מריץ preflight health check (Claude, Gemini, S3, Kling) לפני כל task
- מנהל ניתוב עם conditional edges ב-LangGraph

### Agent 2 — Content Agent (Claude Sonnet 4.5)
- מחקר + copywriting בקריאת API אחת
- מייצר batch שלם (עד 200 comments / 50 posts/reels) בתגובה JSON מובנית
- persona rotation אוטומטי לcomments
- לreels: מייצר script מלא עם 3 סצנות, visual_description, narrator_text, audio_mood
- תומך עברית ואנגלית natively
- מקבל retry feedback מהValidator עד 2 ניסיונות

### Agent 3 — Image Agent (Gemini Imagen 4)
- יצירת Style Reference image לפני ה-batch (anchor ויזואלי)
- יצירת תמונות בממדי פלטפורמה נכונים: 1:1, 9:16
- 4 ניסיונות חוזרים עם backoff על 503/overload

### Agent 4 — Video Agent (Kling via kie.ai)
ראה סעיף 4 לפירוט מלא.

### Agent 5 — Content Validator (Claude + langdetect)
שכבה דטרמיניסטית:
- בדיקת שפה via langdetect
- בדיקת אורך לפי מגבלות פלטפורמה
- Jaccard similarity < 0.7 לזיהוי כפילויות ב-batch

שכבה LLM:
- ניקוד naturalness + tone (1-10) via Claude
- דחייה אם ציון < 6 עם feedback ספציפי לAgent המקורי
- מקסימום 2 retries לפריט
- לvideo: אם וידאו כבר נוצר — אין retry (יקר מדי)

---

## 4. Video Agent — Kling Pipeline (v5.0)

### 4.1 Kling Configuration
```
Provider:        kie.ai
T2V Model:       kling-2.6/text-to-video    (קליפ ראשון + מוזיקה)
I2V Model:       kling/v2-1-pro              (קליפים 2-3, image-to-video)
Clip duration:   KIE_CLIP_DURATION=10        (5 או 10 שניות — בלבד)
Total duration:  3 × clip_duration           (15s או 30s)
Cost per reel:   ~$0.90 × 3 clips = ~$2.70  (10s clips)
```

### 4.2 Flow לכל Reel

```
1. Content Agent → script עם 3 סצנות (visual_description, narrator_text, audio_mood)
2. generate_video_initial()  → Kling T2V, sound=true → קליפ 1 עם מוזיקה AI
3. extract_last_frame()      → PNG מהפריים האחרון של קליפ 1 (cached)
4. extend_video() × 1        → Kling I2V מפריים קליפ 1 → קליפ 2
5. generate_video_from_frame() → Kling I2V מפריים קליפ 1 (payoff) → קליפ 3
6. download_and_merge_clips_s3() → FFmpeg:
   - -stream_loop -1 על קליפ 1 (מוזיקה לאורך כל הוידאו)
   - concat 3 קליפי וידאו
   - atrim לmatch total_duration
7. mix_tts_voice()           → Google Cloud TTS (Wavenet) + מוזיקה ב-25% volume
8. burn_captions()           → FFmpeg, עברית RTL / אנגלית, מתוזמן לסצנות
9. upload to S3              → video.mp4 + script.txt + content.json
```

### 4.3 Prompt Architecture

**`_build_initial_prompt`** — סצנה 1 (T2V):
- visual_description + visual_style_descriptor + canonical_subject
- 9:16 vertical, no text overlays, professional grade

**`_build_extend_prompt`** — סצנות 2-N (I2V):
- continuity lock: entry_state, subject lock
- הפרדה בין open journeys לclosed content (food/fitness)
- same location/lighting for closed, new locations allowed for open

**`_build_payoff_prompt`** — סצנה אחרונה (I2V מפריים סצנה 1):
- FINAL SCENE — camera push-in בלבד
- אסור: אנימציה, חזרה על פעולות קודמות

### 4.4 Audio Stack

```
קליפ 1 (Kling T2V, sound=true)  → מוזיקה AI-generated
               ↓
FFmpeg -stream_loop -1           → מוזיקה לאורך כל הוידאו (15s או 30s)
               ↓
Google Cloud TTS (Wavenet)       → נרטיב דובר לכל סצנה בנפרד
               ↓
mix_tts_voice()                  → music_volume=0.25, voice_volume=1.0
               ↓
burn_captions()                  → caption_text (עברית) / caption_text_en (אנגלית)
```

### 4.5 Extend Loop עם Node-Level Checkpoint
```python
for extend_idx in range(completed_extends, required_extends):
    current_video_ref = await extend_video(...)
    completed_extends = extend_idx + 1       # ← saved to state
    all_video_refs.append(current_video_ref) # ← saved to state
```
קריסה ב-extend 1 מתוך 2 → resume מ-extend 2, לא מההתחלה.

---

## 5. מערכת Checkpoint תלת-שכבתית

### Tier 1 — Batch Level
- כל פריט רץ ב-try/except עצמאי
- כשל בפריט 2 לא מבטל פריטים 1 ו-3
- upload מיידי ל-S3 על הצלחה

### Tier 2 — Pipeline Level
- LangGraph MemorySaver + thread_id ייחודי לכל פריט
- retry של video שנכשל → דולג על Content Agent שכבר הצליח

### Tier 3 — Node Level (Video)
- `completed_extends` + `all_video_refs` נשמרים לstate אחרי כל extend
- `current_video_ref` נשמר לstate
- קריסה בplip 2 מתוך 3 → resume מקליפ 3

---

## 6. QA Layer — Infrastructure

### Health Checks (Pre-flight)
לפני כל task, בדיקת זמינות כל השירותים הנדרשים:
- **Claude** — lightweight completion (max_tokens=10)
- **Gemini** — list_models
- **S3** — HeadBucket
- **Kling** — GET /api/v1/jobs/queryTask (expects 400/404 = API up)

```
PIPELINE_SERVICES = {
    "text_only":  ["claude", "s3"],
    "text_image": ["claude", "gemini", "s3"],
    "full_video": ["claude", "gemini", "kling", "s3"],
}
```

### Circuit Breakers
```
Closed    → בקשות עוברות נורמלית
Open      → 5 כשלות ב-120 שניות → חסימה מיידית
Half-Open → probe כל 60 שניות → סגירה על הצלחה
```

### Retry Policy
| Service | Timeout | Retries | Backoff |
|---|---|---|---|
| Claude API | 30s | 3 | exponential, base 2s, max 30s |
| Imagen | 45s | 3 | 10s, 20s, 40s |
| Kling T2V/I2V | 300s poll | 4 | 10s, 30s, 60s |
| S3 | 30s | 3 | exponential |

### `/health` Endpoint
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

---

## 7. S3 Output Structure

### Folder Hierarchy
```
{bucket}/
  videos/{task_id}/
    manifest.json
    {platform}/
      item_{n}/
        video.mp4          ← merged video with music + TTS + captions
        script.txt         ← scene-by-scene script
        content.json       ← captions, hashtags, narrator_text
        thumbnail.png      ← style reference image (item_0 only)
  posts/{task_id}/
    manifest.json
    {platform}/
      item_{n}/
        image.png
        content.json
  comments/{task_id}/
    manifest.json
    {platform}/
      item_0/
        content.json       ← all comments as JSON array
  kling-temp/              ← intermediate clips, cleaned up after merge
```

### manifest.json
```json
{
  "task_id": "uuid",
  "status": "completed | partial | failed",
  "quantity_requested": 1,
  "quantity_delivered": 1,
  "quantity_failed": 0,
  "total_cost_usd": 2.72,
  "cost_saved_by_checkpoint": 0.00,
  "failed_items": [],
  "assets": [...]
}
```

---

## 8. מגבלות ותצורה

| פרמטר | ערך |
|---|---|
| Max comments per task | 200 |
| Max posts/stories/reels per task | 50 |
| Concurrent text_only | 48 |
| Concurrent text_image | 18 |
| Concurrent full_video | 8 |
| Validator LLM score threshold | 6/10 |
| Jaccard similarity threshold | 0.7 |
| Max retries per item | 2 |
| Circuit breaker threshold | 5 failures / 120s |
| Clip duration (Kling) | 5s או 10s בלבד |

---

## 9. Frontend — Testing UI

### Stack
Next.js 14 (App Router) + TypeScript + Tailwind CSS + TanStack Query v5  
רץ על `http://localhost:3000`, מחובר לbackend על `http://localhost:8000`

### Pages

| נתיב | תיאור |
|---|---|
| `/` | New Task form — platform, content type, language, quantity, description |
| `/tasks/[taskId]` | Task detail — pipeline status, metrics, result gallery |
| `/tasks` | All Tasks — רשימת כל המשימות עם פילטרים |
| `/health-check` | Service health + circuit breaker states |
| `/history` | היסטוריית משימות לפי יום |
| `/usage` | ניתוח עלויות לפי סוג תוכן ופלטפורמה |

### Components מרכזיים

**Sidebar** — ניווט מתקפל עם health dot שמתעדכן כל 15 שניות.

**PipelineStrip** — 5 nodes ויזואליים:
```
Orchestrator → Content → Image → Video → Validator
```

**ClipProgressDots (VeoExtendDots)** — 3 נקודות progress לreels:
```
● clip 1 (Xs) · clip 2 (+Xs) · clip 3 (+Xs)
```
מוצג כמלא על completed, pulsing על processing.

**MetricsLine** — delivered/total, failed count, total_cost_usd, cost_saved_by_checkpoint.

**ResultGallery** — ניתוב אוטומטי לפי content_type:
- `comment` → CommentsGrid (RTL-aware, persona pill, ✓/✗ validation badge, copy button)
- `post/story` → PostsGrid (תמונות S3 presigned, caption, hashtags RTL-aware, copy button)
- `reels` → ReelsGrid (`<video controls>`, download link, clip progress dots, copy button)

### Hooks (כולל polling)
- `useTask` — backoff polling: 2s→5s→10s→20s, עוצר בסיום
- `useAllTasks` — poll כל 5 שניות
- `useHealth` — poll כל 15 שניות
- `useRecentTasks` — poll כל 10 שניות
- כל ה-hooks: `refetchIntervalInBackground: false` — עוצר polling כשהtab מוסתר

### Error Handling
- כל עמוד מציג שגיאה ברורה אם ה-API נכשל (לא spinner אינסופי)
- `app/error.tsx` — global error boundary לכל קריסת React
- content query error מוצג בעמוד task detail
- retry button על שגיאות fetch

---

## 10. Post-MVP Roadmap

- PostgreSQL + Alembic (מחליף in-memory task store)
- Celery + Redis (distributed workers)
- CloudFront CDN (asset delivery)
- Prometheus + Grafana (observability)
- Fallback routing: Claude → GPT-4o, Imagen → DALL-E 3
- Content Safety Agent (pre-upload screening)
- Auth + Rate Limiting על ה-API Gateway
- WebSocket real-time updates (מחליף polling)
- Pagination על task lists
