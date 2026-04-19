import type { TaskStatusResponse } from '@/types/api';

interface MetricsLineProps {
  task: TaskStatusResponse;
}

export function MetricsLine({ task }: MetricsLineProps) {
  const {
    quantity_delivered,
    quantity_requested,
    quantity_failed,
    total_cost_usd,
    cost_saved_by_checkpoint,
  } = task;

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-zinc-600">
      <span>
        <span className="font-medium text-zinc-900">{quantity_delivered}</span>
        <span className="text-zinc-400">/{quantity_requested}</span>
        <span className="ml-1 text-zinc-500">done</span>
      </span>

      {quantity_failed > 0 && (
        <span className="text-rose-600">
          <span className="font-medium">{quantity_failed}</span> failed
        </span>
      )}

      <span>
        <span className="font-medium text-zinc-900">
          ${total_cost_usd.toFixed(2)}
        </span>
        {cost_saved_by_checkpoint > 0 && (
          <span className="text-emerald-600 ml-1">
            (saved ${cost_saved_by_checkpoint.toFixed(2)})
          </span>
        )}
      </span>
    </div>
  );
}
