import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getTask, getTaskContent } from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import type { TaskStatusResponse, TaskContentResponse } from '@/types/api';

const TERMINAL = new Set(['completed', 'partial', 'failed']);

function isTerminal(status: string | undefined): boolean {
  return status ? TERMINAL.has(status) : false;
}

function backoffMs(pollCount: number): number {
  if (pollCount < 5)  return 2_000;
  if (pollCount < 14) return 5_000;
  if (pollCount < 22) return 10_000;
  return 20_000;
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
    refetchIntervalInBackground: false,
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
    refetchIntervalInBackground: false,
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
