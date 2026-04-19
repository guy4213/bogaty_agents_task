export type Platform = 'instagram' | 'tiktok' | 'twitter' | 'telegram' | 'facebook';
export type ContentType = 'comment' | 'post' | 'story' | 'reels';
export type Language = 'en' | 'he';
export type TaskStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'waiting_for_service';
export type PipelineType = 'text_only' | 'text_image' | 'full_video';

export interface GenerateRequest {
  platform: Platform;
  content_type: ContentType;
  language: Language;
  quantity: number;
  description: string;
}

export interface GenerateResponse {
  task_id: string;
  status: TaskStatus;
  message: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: TaskStatus;
  platform: string;
  content_type: string;
  quantity_requested: number;
  quantity_delivered: number;
  quantity_failed: number;
  total_cost_usd: number;
  cost_saved_by_checkpoint: number;
  manifest_s3_key: string | null;
  presigned_manifest_url: string | null;
  errors: string[];
}

export interface AssetRecord {
  item_index: number;
  asset_type: string;
  file_format: string;
  s3_key: string;
  validation_passed: boolean | null;
  generation_cost_usd?: number;
  note?: string;
  content?: unknown;
  download_url?: string | null;
}

export interface TaskContentResponse {
  task_id: string;
  status: string;
  platform: string;
  content_type: string;
  language: string;
  quantity_requested: number;
  quantity_delivered: number;
  total_cost_usd: number;
  assets: AssetRecord[];
}

export interface TaskListItem {
  task_id: string;
  status: TaskStatus;
  platform: string;
  content_type: string;
  quantity: number;
  items_completed: number;
  items_failed: number;
  total_cost_usd: number;
  created_at: string;
}

export interface ServiceHealth {
  service: string;
  status: string;
  circuit_state: string;
  latency_ms: number | null;
  error: string | null;
}

export interface HealthResponse {
  overall: string;
  services: ServiceHealth[];
  timestamp: string;
}

export interface CommentItem {
  text: string;
  persona?: string;
  hashtags?: string[];
  scene_markers?: unknown[];
  caption_per_scene?: unknown;
}

export interface ValidationResult {
  item_id: number;
  passed: boolean;
  score: number;
  errors: string[];
  retry_feedback: string | null;
}
