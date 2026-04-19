import { useQuery } from '@tanstack/react-query';
import { getTask, getTaskContent } from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import type { TaskStatusResponse, TaskContentResponse } from '@/types/api';

const TERMINAL = new Set(['completed', 'partial', 'failed']);

function isTerminal(status: string | undefined): boolean {
  return status ? TERMINAL.has(status) : false;
}

export function useTask(taskId: string) {
  const statusQuery = useQuery<TaskStatusResponse>({
    queryKey: queryKeys.task(taskId),
    queryFn: () => getTask(taskId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return isTerminal(status) ? false : 2000;
    },
    enabled: Boolean(taskId),
  });

  const contentQuery = useQuery<TaskContentResponse | null>({
    queryKey: queryKeys.taskContent(taskId),
    queryFn: async () => {
      const result = await getTaskContent(taskId);
      if ('message' in result) return null;
      return result as TaskContentResponse;
    },
    refetchInterval: (query) => {
      const status = statusQuery.data?.status;
      if (isTerminal(status)) return false;
      if (query.state.data === null) return 3000;
      return false;
    },
    enabled: Boolean(taskId) && !isTerminal('pending'),
    retry: 1,
  });

  return {
    status: statusQuery,
    content: contentQuery,
    isLoading: statusQuery.isLoading,
    isTerminal: isTerminal(statusQuery.data?.status),
  };
}
