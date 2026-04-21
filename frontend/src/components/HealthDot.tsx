'use client';

import { useHealth } from '@/hooks/useHealth';

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export function HealthDot() {
  const { data, allHealthy, isLoading } = useHealth();

  if (isLoading) {
    return (
      <div
        className="w-2.5 h-2.5 rounded-full bg-zinc-400 animate-pulse"
        title="Checking health..."
      />
    );
  }

  const tooltip = data
    ? data.services
        .map((s) => `${s.service}: ${s.status} (${s.circuit_state})`)
        .join('\n')
    : 'Health check failed';

  return (
    <button
      type="button"
      onClick={() => window.open(`${BASE_URL}/health`, '_blank')}
      title={tooltip}
      className="flex items-center gap-1.5 group"
    >
      <div
        className={`w-2.5 h-2.5 rounded-full transition-colors ${
          allHealthy ? 'bg-emerald-500' : 'bg-rose-500'
        }`}
      />
      <span className="text-xs text-zinc-500 group-hover:text-zinc-700 hidden sm:inline">
        {allHealthy ? 'healthy' : 'degraded'}
      </span>
    </button>
  );
}
