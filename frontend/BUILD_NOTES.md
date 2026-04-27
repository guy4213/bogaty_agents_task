# Build Notes

## What was built

Full `frontend/` Next.js 14 app with:

- **New Task form** (`/`) — platform, content type, language, quantity, description, cost estimator
- **Task Detail** (`/tasks/[taskId]`) — pipeline strip, metrics, result gallery
- **All Tasks** (`/tasks`) — filterable table by status/type/platform
- **History** (`/history`) — timeline grouped by day
- **Usage & Cost** (`/usage`) — cost breakdown by content type and platform
- **Health Check** (`/health-check`) — service health + circuit breaker states
- **Sidebar** — collapsible nav with health dot (polls every 15s)
- **PipelineStrip** — 5 nodes (Orchestrator→Content→Image→Video→Validator) with inferred states
- **ClipProgressDots (VeoExtendDots)** — 3-dot progress for Kling reels (clip 1 + 2 extends), configurable count and duration
- **MetricsLine** — delivered/total, failed count, cost, checkpoint savings
- **ResultGallery** — routes to CommentsGrid, PostsGrid (1:1 or 9:16), or ReelsGrid
- **CommentsGrid / CommentCard** — RTL-aware, persona pill, validation badge, copy button
- **PostsGrid / PostCard** — S3 presigned images, caption, hashtags RTL-aware, copy button, Style Anchor badge
- **ReelsGrid / ReelCard** — `<video controls>`, download link, clip progress dots, copy button
- **Global error boundary** (`app/error.tsx`) — catches unhandled React errors
- All hooks: `useTask`, `useHealth`, `useRecentTasks`, `useAllTasks`
- All hooks: `refetchIntervalInBackground: false` — polling pauses when tab is hidden

## Ambiguous backend shapes and resolutions

### 1. Comment content JSON structure
The backend stores the entire batch of comments in one JSON file (`item_0/content.json`). `CommentsGrid` probes for `Array`, `comments`, `generated_texts`, `items` keys, and falls back to a single-item object.

### 2. `completed_extends` not exposed in API
The `completed_extends` field lives in the LangGraph state but is not serialized into `TaskStatusResponse`. For completed reels, all 3 dots are shown filled. During processing with no video assets yet, dots show as pending.

### 3. Validation score not available from content endpoint
The `/tasks/{id}/content` endpoint's assets have `validation_passed` (boolean) but no numeric score. `CommentCard` shows ✓/✗. The score is inside the LangGraph state but not written to the content API response.

### 4. Per-node pipeline status inferred
The task status endpoint returns a coarse `status` string, not per-node states. `PipelineStrip` infers states from `status` + `content_type` + `quantity_delivered`.

### 5. Style Anchor identification
The backend flags the style anchor via `style_reference_image` in state but does not include an `is_anchor` flag in manifest assets. Item index 0 is treated as the anchor.

### 6. `TaskStatus.waiting_for_service` not in original spec
The backend models.py includes `waiting_for_service` as a valid TaskStatus. Added to types and badge map.

## Deferred items

- Numeric validation scores (requires backend to expose them in the content endpoint)
- Real `completed_extends` live tracking (requires polling state endpoint or SSE)
- Thumbnail display in ReelCard (thumbnail stored separately but not differentiated in manifest)
- WebSocket real-time updates (currently polling-based)
