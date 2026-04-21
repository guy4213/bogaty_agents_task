# Build Notes

## What was built

Full `frontend/` Next.js 14 app with:

- **New Task form** (`/`) — platform, content type, language, quantity, description
- **Task Detail** (`/tasks/[taskId]`) — pipeline strip, metrics, result gallery
- **Header** — app name, health dot (polls every 15s), recent tasks dropdown
- **PipelineStrip** — 5 nodes (Orchestrator→Content→Image→Video→Validator) with inferred states
- **VeoExtendDots** — 4-dot progress for reels (initial 8s + 3×7s extends)
- **MetricsLine** — delivered/total, failed count, cost, checkpoint savings
- **ResultGallery** — routes to CommentsGrid, PostsGrid (1:1 or 9:16), or ReelsGrid
- **CommentsGrid / CommentCard** — RTL-aware, persona pill, validation badge
- **PostsGrid / PostCard** — S3 presigned images, caption, hashtags, Style Anchor badge on first item
- **ReelsGrid / ReelCard** — `<video controls>`, download link, VeoExtendDots
- **StyleAnchorBadge** — absolute-positioned 🎨 pill on image cards
- All hooks: `useTask`, `useHealth`, `useRecentTasks`

## Ambiguous backend shapes and resolutions

### 1. Comment content JSON structure
The backend stores the entire batch of comments in one JSON file (`item_0/content.json`) with `generated_texts` as a list of dicts. The exact top-level key is unknown without running the agent. `CommentsGrid` probes for `Array`, `comments`, `generated_texts`, `items` keys, and falls back to a single-item object.

### 2. `completed_extends` not exposed in API
The `completed_extends` field lives in the LangGraph state but is not serialized into `TaskStatusResponse`. For completed reels, all 4 dots are shown filled. During processing with no video assets yet, dots show as pending. Documented in `VeoExtendDots`.

### 3. Validation score not available from content endpoint
The `/tasks/{id}/content` endpoint's assets have `validation_passed` (boolean) but no numeric score. `CommentCard` shows ✓/✗ instead of `score 8/10` as specified. The score is inside the LangGraph state validation_results but not written to the content API response.

### 4. Per-node pipeline status inferred
The task status endpoint returns a coarse `status` string, not per-node states. `PipelineStrip` infers states from `status` + `content_type` + `quantity_delivered`. This is an approximation.

### 5. Style Anchor identification
The backend flags the style anchor image via `style_reference_image` in state, but does not include an `is_anchor` flag in the manifest assets. The first image in the batch (item_index 0) is treated as the anchor, consistent with how runner.py generates the reference before launching parallel items.

### 6. `TaskStatus.waiting_for_service` not in original spec
The backend models.py includes `waiting_for_service` as a valid TaskStatus. Added to types and badge map.

## Deferred items

- Numeric validation scores (requires backend to expose them in the content endpoint)
- Real `completed_extends` live tracking (requires polling state endpoint or SSE)
- Thumbnail display in ReelCard (thumbnail is stored as a separate PNG but not differentiated from image assets in the manifest)
