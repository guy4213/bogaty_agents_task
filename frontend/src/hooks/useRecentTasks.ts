import { useQuery } from '@tanstack/react-query';
import { listTasks } from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import type { TaskListItem } from '@/types/api';

export function useRecentTasks() {
  return useQuery<TaskListItem[]>({
    queryKey: queryKeys.tasks,
    queryFn: listTasks,
    refetchInterval: 10000,
    refetchIntervalInBackground: false,
    select: (data) =>
      [...data]
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
        )
        .slice(0, 5),
  });
}
