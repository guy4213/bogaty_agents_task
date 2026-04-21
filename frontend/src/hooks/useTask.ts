import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getTask, getTaskContent } from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import type { TaskStatusResponse, TaskContentResponse } from '@/types/api';

const TERMINAL = new Set(['completed', 'partial', 'failed']);

function isTerminal(status: string | undefined): boolean {
  return status ? TERMINAL.has(status) : false;
}

// Stepped backoff: fast start → slow cruise for long-running video tasks
function backoffMs(pollCount: number): number {
  if (pollCount < 5)  return 2_000;   // 0–10 s   → every 2 s  (catches fast state changes)
  if (pollCount < 14) return 5_000;   // 10–55 s  → every 5 s
  if (pollCount < 22) return 10_000;  // 55–135 s → every 10 s (most tasks finish here)
  return 20_000;                       // 135 s+   → every 20 s (long video jobs)
}

export function useTask(taskId: string) {
  const statusPollCount  = useRef(0);
  const contentPollCount = useRef(0);

  const statusQuery = useQuery<TaskStatusResponse>({
    queryKey: queryKeys.task(taskId),
    queryFn: () => {
      statusPollCount.current += 1;
      return getTask(taskId);
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return isTerminal(status) ? false : backoffMs(statusPollCount.current);
    },
    enabled: Boolean(taskId),
  });

  const contentQuery = useQuery<TaskContentResponse | null>({
    queryKey: queryKeys.taskContent(taskId),
    queryFn: async () => {
      contentPollCount.current += 1;
      const result = await getTaskContent(taskId);
      if ('message' in result) return null;
      return result as TaskContentResponse;
    },
    refetchInterval: () => {
      const status = statusQuery.data?.status;
      return isTerminal(status) ? false : backoffMs(contentPollCount.current);
    },
    enabled: Boolean(taskId),
    retry: 1,
  });

  return {
    status: statusQuery,
    content: contentQuery,
    isLoading: statusQuery.isLoading,
    isTerminal: isTerminal(statusQuery.data?.status),
  };
}
