'use client';

import { useRouter } from 'next/navigation';
import { useRecentTasks } from '@/hooks/useRecentTasks';
import type { TaskListItem } from '@/types/api';

const DOT_STYLE: Record<string, React.CSSProperties> = {
  completed: { background: 'var(--success)' },
  processing: { background: 'var(--accent-light)', boxShadow: '0 0 6px var(--accent-light)', animation: 'pulse 1.5s infinite' },
  partial: { background: 'var(--warning)' },
  failed: { background: 'var(--danger)' },
  pending: { background: 'var(--fg3)' },
  waiting_for_service: { background: 'var(--warning)', animation: 'pulse 1.5s infinite' },
};

const BADGE_STYLE: Record<string, React.CSSProperties> = {
  completed: { background: 'rgba(34,197,94,0.1)', color: '#4ade80' },
  processing: { background: 'rgba(99,102,241,0.12)', color: 'var(--accent-light)' },
  partial: { background: 'rgba(245,158,11,0.12)', color: '#fbbf24' },
  failed: { background: 'rgba(239,68,68,0.1)', color: '#f87171' },
  pending: { background: 'var(--surface3)', color: 'var(--fg3)' },
  waiting_for_service: { background: 'rgba(245,158,11,0.12)', color: '#fbbf24' },
};

function TaskRow({ task, onClick }: { task: TaskListItem; onClick: () => void }) {
  const dotStyle = DOT_STYLE[task.status] ?? DOT_STYLE['pending'];
  const badgeStyle = BADGE_STYLE[task.status] ?? BADGE_STYLE['pending'];

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-3 px-5 py-[11px] text-left transition-colors duration-100"
      style={{ borderBottom: '1px solid var(--border)' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface2)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; }}
    >
      <span className="w-[7px] h-[7px] rounded-full flex-shrink-0" style={dotStyle} />
      <span className="flex-1 min-w-0">
        <span className="block text-[12.5px] font-medium truncate" style={{ color: 'var(--fg1)' }}>
          {task.task_id.slice(0, 8)}…
        </span>
        <span className="block text-[11px] font-mono mt-0.5" style={{ color: 'var(--fg3)' }}>
          {task.platform} · {task.content_type} · {task.items_completed}/{task.quantity}
        </span>
      </span>
      <span
        className="text-[10.5px] font-semibold px-[7px] py-[2px] rounded flex-shrink-0"
        style={badgeStyle}
      >
        {task.status}
      </span>
      <span className="text-[11.5px] font-mono flex-shrink-0" style={{ color: 'var(--fg3)' }}>
        {task.total_cost_usd > 0 ? `$${task.total_cost_usd.toFixed(2)}` : '—'}
      </span>
    </button>
  );
}

export function RecentTasksPanel() {
  const router = useRouter();
  const { data: tasks, isLoading } = useRecentTasks();

  return (
    <div
      className="flex flex-col flex-1 rounded-[var(--radius)] overflow-hidden"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
    >
      <div
        className="px-5 py-3 flex items-center justify-between"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5" style={{ color: 'var(--accent-light)' }}>
            <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.3" />
            <path d="M7 4v3.5l2 1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          <span className="text-[13px] font-semibold" style={{ color: 'var(--fg1)' }}>
            Recent Tasks
          </span>
        </div>
        <button
          type="button"
          className="text-[11px] font-medium px-2 py-1 rounded transition-colors"
          style={{ border: '1px solid var(--border2)', color: 'var(--fg2)' }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface2)'; (e.currentTarget as HTMLElement).style.color = 'var(--fg1)'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--fg2)'; }}
          onClick={() => router.push('/tasks')}
        >
          View all →
        </button>
      </div>

      <div className="flex flex-col flex-1">
        {isLoading && (
          <p className="px-5 py-8 text-sm text-center" style={{ color: 'var(--fg3)' }}>
            Loading…
          </p>
        )}
        {!isLoading && (!tasks || tasks.length === 0) && (
          <p className="px-5 py-8 text-[13px] text-center" style={{ color: 'var(--fg3)' }}>
            No tasks yet. Submit a brief to get started.
          </p>
        )}
        {tasks?.map((task) => (
          <TaskRow
            key={task.task_id}
            task={task}
            onClick={() => router.push(`/tasks/${task.task_id}`)}
          />
        ))}
      </div>
    </div>
  );
}
