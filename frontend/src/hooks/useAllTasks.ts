import { useQuery } from '@tanstack/react-query';
import { listTasks } from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import type { TaskListItem } from '@/types/api';

export function useAllTasks() {
  return useQuery<TaskListItem[]>({
    queryKey: queryKeys.tasks,
    queryFn: listTasks,
    refetchInterval: 5000,
  });
}
