# Content Engine — Production Architecture & Design Document
## Autonomous Multi-Modal Content Generation System

**Author:** Guy Franses
**Date:** April 2026
**Version:** 4.0 — Post-Optimization

---

## 1. Executive Summary

Content Engine הוא מערכת אוטונומית לייצור תוכן מולטי-מודאלי. המערכת מקבלת brief טקסטואלי קצר ומייצרת assets מוכנים לפרסום עבור Instagram, TikTok, Twitter/X, Telegram ו-Facebook — בעברית ואנגלית.

הגרסה הנוכחית (4.0) מייצגת שיפור משמעותי על גרסה 3.0 בתחום יעילות ה-API, יציבות הפיפליין, וחסכון בעלויות הפקה.

---

## 2. ארכיטקטורת המערכת

### 2.1 Pipeline Routing

```
content_type  →  pipeline_type  →  agent chain
─────────────────────────────────────────────────────────────
comment       →  text_only      →  Orchestrator → Content Agent → Validator
post/story    →  text_image     →  Orchestrator → Content Agent → Image Agent → Validator
reels         →  full_video     →  Orchestrator → Content Agent → Image Agent → Video Agent → Validator
```

### 2.2 Stack טכנולוגי

| שכבה | טכנולוגיה |
|---|---|
| API Server | FastAPI (Python 3.12) + Uvicorn |
| Agent Orchestration | LangGraph 1.x + MemorySaver |
| Text Generation | Claude Sonnet 4.5 (Anthropic) |
| Image Generation | Nano Banana 2 — Gemini 3.1 Flash Image |
| Video Generation | Veo 3.1 Full — Vertex AI |
| Asset Storage | AWS S3 via boto3 |
| Temp Video Storage | Google Cloud Storage (GCS) |
| Media Processing | FFmpeg via static-ffmpeg |
| Observability | LangSmith + structured logging |
| Containerisation | Docker + docker-compose |

---

## 3. Agent Definitions

### Agent 1 — Orchestrator
- מנתח פרמטרים, מפרק batches לsub-tasks, קובע pipeline_type
- מריץ preflight health check לפני כל task
- מנהל ניתוב עם conditional edges ב-LangGraph

### Agent 2 — Content Agent (Claude Sonnet 4.5)
- מחקר + copywriting בקריאת API אחת
- מייצר batch שלם (עד 50 פריטים) בתגובה JSON מובנית אחת
- persona rotation אוטומטי (10 פרסונות + רמות enthusiasm אקראיות)
- תומך עברית ואנגלית natively
- מקבל retry feedback מהValidator עד 2 ניסיונות

### Agent 3 — Image Agent (Nano Banana 2)
- יצירת תמונות בממדי פלטפורמה נכונים: 1:1, 9:16
- Style Reference: התמונה הראשונה מהווה anchor ויזואלי לכל שאר התמונות ב-batch
- 4 ניסיונות חוזרים עם backoff על 503/overload

### Agent 4 — Video Agent (Veo 3.1 Full)
ראה סעיף 4 לפירוט מלא של השיפורים.

### Agent 5 — Content Validator (Claude + langdetect)
שכבה דטרמיניסטית:
- בדיקת שפה via langdetect
- בדיקת אורך לפי מגבלות פלטפורמה
- Jaccard similarity < 0.7 לzיהוי כפילויות ב-batch

שכבה LLM:
- ניקוד naturalness + tone (1-10) via Claude
- דחייה אם ציון < 6 עם feedback ספציפי לAgent המקורי
- מקסימום 2 retries לפריט

---

## 4. Video Agent — שיפורי יעילות v4.0

### 4.1 Veo Configuration
```
Model:           veo-3.1-generate-001
Initial clip:    8 seconds
Each extend:     7 seconds
Target duration: 29 seconds (1 initial + 3 extends)
Cost per reel:   ~$11.60 ($0.40/sec × 29s)
```

### 4.2 Prompt Architecture
ארבעה סוגי promptים מובחנים:

**`_build_initial_prompt`** — סצנה 1:
- קונפיגורציה מלאה של visual style, canonical subject, camera framing
- 9:16 vertical, 1080×1920, no text overlays

**`_build_extend_prompt`** — סצנות 2-N:
- continuity lock: entry_state, subject lock
- style anchor מסצנה 1
- הפרדה בין open journeys (travel, real estate) לclosed content (food, fitness)

**`_build_payoff_prompt`** — סצנה אחרונה:
- FINAL SCENE — camera push-in בלבד
- אסור: אנימציה, חזרה על פעולות קודמות

**`_build_extend_prompt` עם `content_category`** — שמירת קוהרנטיות סמנטית לאורך כל הסצנות

### 4.3 Extend Loop עם Node-Level Checkpoint
```python
# כל extend נשמר לstate לפני שהלולאה ממשיכה
for extend_idx in range(completed_extends, required_extends):
    current_video_ref = await extend_video(...)
    completed_extends = extend_idx + 1          # ← saved to state
    all_video_refs.append(current_video_ref)    # ← saved to state
```
קריסה ב-extend 2 מתוך 3 → resume מ-extend 3, לא מההתחלה.

### 4.4 Payoff Scene — Image-to-Video
הסצנה האחרונה נוצרת מה-frame האחרון של סצנה 1:
- עקביות ויזואלית מושלמת בין פתיחה לסיום
- `generate_video_from_frame` במקום `extend_video`

---

## 5. אופטימיזציות v4.0 — פירוט

### Fix 1 — Exponential Backoff על Veo Poll
**לפני:** poll כל 5 שניות ×120 קריאות = 120 API calls לgeneration
**אחרי:** 5s → 10s → 20s → 30s → 30s... = ~25 API calls
```python
interval = 5
while not operation.done:
    await asyncio.sleep(interval)
    interval = min(interval * 2, 30)
```

### Fix 2 — הפרדת Overload Retry מVariation
**לפני:** overload → מנסה variation חדשה = קריאת Veo חדשה ויקרה
**אחרי:** overload → מנסה שוב אותה variation (עד 3 פעמים) → variation חדשה רק על דחיית תוכן
```
overload attempt 1 → wait 15s → retry SAME variation
overload attempt 2 → wait 30s → retry SAME variation
overload attempt 3 → wait 60s → retry SAME variation
content rejection  → advance to next variation
```
**חיסכון ישיר:** מניעת תשלום כפול על Veo overloads.

### Fix 3 — הורדת GCS קליפים במקביל
**לפני:** 4 קליפים בסדרה = ~25 שניות המתנה
**אחרי:** 4 קליפים במקביל via ThreadPoolExecutor = ~7 שניות
```python
with ThreadPoolExecutor(max_workers=len(gcs_uris)) as executor:
    futures = [executor.submit(_download_clip, uri, i) for i, uri in enumerate(gcs_uris)]
    clip_paths = [f.result() for f in futures]
```

### Fix 4 — Cache Frame של סצנה 1
**לפני:** הורדה מחדש של קליפ סצנה 1 (15-20MB) כדי לחלץ פריים אחד
**אחרי:** הפריים נחלץ ונשמר בזיכרון מיד לאחר יצירת הקליפ הראשון
```python
scene1_frame_cache: bytes | None = None
# נשמר אחרי initial generation, נשמש ב-payoff
```

### Fix 5 — ניקוי אוטומטי GCS
**לפני:** קליפי temp נשארים לצמיתות ב-GCS
**אחרי:** מחיקה אוטומטית אחרי merge, ב-asyncio.gather
```python
async def cleanup_veo_temp_files(gcs_uris, project_id):
    # never raises — logs only
    # "Cleaned up N/M veo-temp blobs"
```

---

## 6. מערכת Checkpoint תלת-שכבתית

### Tier 1 — Batch Level
- כל פריט רץ ב-try/except עצמאי
- כשל בפריט 2 לא מבטל פריטים 1 ו-3
- upload מיידי ל-S3 על הצלחה

### Tier 2 — Pipeline Level
- LangGraph MemorySaver + thread_id ייחודי לכל פריט
- retry של video שנכשל → דולג על Content + Image nodes שכבר הצליחו

### Tier 3 — Node Level (Video)
- `completed_extends` נשמר לstate אחרי כל extend
- `all_video_refs` נשמר לstate אחרי כל extend
- קריסה ב-extend 3/4 → resume מ-extend 4

---

## 7. QA Layer — Infrastructure

### Health Checks (Pre-flight)
לפני כל task, בדיקת זמינות:
- Claude API — lightweight completion
- Gemini API — list_models
- AWS S3 — HeadBucket
- Veo — circuit breaker status

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
| Nano Banana 2 | 45s | 3 | 10s, 20s, 40s |
| Veo 3.1 | 90s | 2 | per variation (Fix 2) |
| S3 | 30s | 3 | exponential |

### `/health` Endpoint
```json
{
  "service": "claude",
  "status": "healthy",
  "circuit_state": "closed",
  "latency_ms": 312,
  "error": null
}
```

---

## 8. S3 Structure & Manifest

### Folder Hierarchy
```
content-engine-prod/
  tasks/{task_id}/
    manifest.json
    {platform}/
      {content_type}/
        item_{n}/
          video.mp4 / image.png / caption.txt
          script.txt
          metadata.json
```

### manifest.json
```json
{
  "task_id": "uuid",
  "status": "completed | partial | failed",
  "quantity_requested": 3,
  "quantity_delivered": 3,
  "quantity_failed": 0,
  "total_cost_usd": 34.80,
  "cost_saved_by_checkpoint": 11.60,
  "failed_items": [],
  "assets": [...]
}
```

---

## 9. מגבלות ותצורה

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

---

## 10. Frontend — Testing UI

### Stack
Next.js 14 + TypeScript + Tailwind CSS + TanStack Query v5
רץ על `http://localhost:3000`, מחובר לbackend על `http://localhost:8000`

### Pages

| נתיב | תיאור |
|---|---|
| `/` | New Task form |
| `/tasks/[taskId]` | Task detail — pipeline status, metrics, result gallery |
| `/tasks` | All Tasks — רשימת כל המשימות |
| `/health-check` | Service health + circuit breaker states |
| `/history` | היסטוריית משימות |

### Components מרכזיים

**Sidebar** — ניווט מתקפל עם health dot שמתעדכן כל 15 שניות. צבע הנקודה משקף מצב כולל: ירוק/צהוב/אדום.

**PipelineStrip** — 5 nodes ויזואליים:
```
Orchestrator → Content → Image → Video → Validator
```
כל node מציג מצב מוסק מ-`status` + `content_type` + `quantity_delivered`.

**VeoExtendDots** — 4 נקודות progress לreels:
```
● initial (8s) · extend 1 (7s) · extend 2 (7s) · extend 3 (7s)
```

**MetricsLine** — שורת מדדים:
- delivered/total
- failed count
- total_cost_usd
- cost_saved_by_checkpoint

**ResultGallery** — ניתוב אוטומטי לפי content_type:
- `comment` → CommentsGrid (RTL-aware, persona pill, ✓/✗ validation badge)
- `post/story` → PostsGrid (תמונות S3 presigned, caption, hashtags, Style Anchor badge 🎨 על הפריט הראשון)
- `reels` → ReelsGrid (`<video controls>`, download link, VeoExtendDots)

### Hooks
- `useTask` — polling אוטומטי בזמן עיבוד
- `useHealth` — poll כל 15 שניות
- `useRecentTasks` — dropdown בTopbar
- `useAllTasks` — עמוד All Tasks

### הערות ידועות (BUILD_NOTES)
- `completed_extends` לא מוחזר מה-API — נקודות Veo מוצגות כמלאות על completed, pending על processing
- ניקוד validator (1-10) לא בresponse — מוצג boolean בלבד
- Style Anchor מזוהה לפי item_index 0 (לא flag מפורש מהbackend)
- `waiting_for_service` status נוסף לtype map

---

## 11. Post-MVP Roadmap

- PostgreSQL + Alembic (מחליף in-memory dataclasses)
- Celery + Redis (distributed workers)
- CloudFront CDN (asset delivery)
- Prometheus + Grafana (observability)
- Fallback routing: Claude → GPT-4o, Nano Banana 2 → DALL-E 3
- Content Safety Agent (pre-upload screening)
- Auth + Rate Limiting על ה-API Gateway