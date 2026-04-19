import type {
  GenerateRequest,
  GenerateResponse,
  TaskStatusResponse,
  TaskContentResponse,
  TaskListItem,
  HealthResponse,
} from '@/types/api';

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchJson<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, text);
  }

  return res.json() as Promise<T>;
}

export function generateTask(req: GenerateRequest): Promise<GenerateResponse> {
  return fetchJson<GenerateResponse>('/generate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export function getTask(taskId: string): Promise<TaskStatusResponse> {
  return fetchJson<TaskStatusResponse>(`/tasks/${taskId}`);
}

export function getTaskContent(
  taskId: string,
): Promise<TaskContentResponse | { task_id: string; status: string; message: string }> {
  return fetchJson(`/tasks/${taskId}/content`);
}

export function getItemContent(
  taskId: string,
  itemIndex: number,
): Promise<{ task_id: string; item_index: number; files: Record<string, unknown> }> {
  return fetchJson(`/tasks/${taskId}/content/${itemIndex}`);
}

export function listTasks(): Promise<TaskListItem[]> {
  return fetchJson<TaskListItem[]>('/tasks');
}

export function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>('/health');
}
