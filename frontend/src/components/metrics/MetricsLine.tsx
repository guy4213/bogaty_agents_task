import type { TaskStatusResponse } from '@/types/api';

interface MetricsLineProps { task: TaskStatusResponse; }

export function MetricsLine({ task }: MetricsLineProps) {
  const { quantity_delivered, quantity_requested, quantity_failed, total_cost_usd, cost_saved_by_checkpoint } = task;

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
      <span style={{ color: 'var(--fg2)' }}>
        <span className="font-semibold font-mono" style={{ color: 'var(--fg1)' }}>{quantity_delivered}</span>
        <span style={{ color: 'var(--fg3)' }}>/{quantity_requested}</span>
        <span className="ml-1" style={{ color: 'var(--fg3)' }}>done</span>
      </span>

      {quantity_failed > 0 && (
        <span style={{ color: 'var(--danger)' }}>
          <span className="font-semibold font-mono">{quantity_failed}</span>
          {' '}failed
        </span>
      )}

      <span>
        <span className="font-semibold font-mono" style={{ color: 'var(--fg1)' }}>
          ${total_cost_usd.toFixed(2)}
        </span>
        {cost_saved_by_checkpoint > 0 && (
          <span className="ml-1 text-[12px]" style={{ color: 'var(--success)' }}>
            (saved ${cost_saved_by_checkpoint.toFixed(2)})
          </span>
        )}
      </span>
    </div>
  );
}
