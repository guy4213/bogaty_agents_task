import { useQuery } from '@tanstack/react-query';
import { getHealth } from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import type { HealthResponse } from '@/types/api';

export function useHealth() {
  const query = useQuery<HealthResponse>({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    refetchInterval: 15000,
    retry: 1,
  });

  const allHealthy =
    query.data?.overall === 'healthy' &&
    query.data.services.every((s) => s.status !== 'down');

  return { ...query, allHealthy };
}
