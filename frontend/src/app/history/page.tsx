'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { Topbar } from '@/components/Topbar';
import { useAllTasks } from '@/hooks/useAllTasks';
import type { TaskListItem } from '@/types/api';

const STATUS_STYLES: Record<string, { dot: string; bg: string; color: string }> = {
  completed:           { dot: 'var(--success)',      bg: 'rgba(34,197,94,0.1)',   color: '#4ade80' },
  processing:          { dot: 'var(--accent-light)', bg: 'rgba(99,102,241,0.12)', color: 'var(--accent-light)' },
  partial:             { dot: 'var(--warning)',       bg: 'rgba(245,158,11,0.12)',color: '#fbbf24' },
  failed:              { dot: 'var(--danger)',        bg: 'rgba(239,68,68,0.1)',  color: '#f87171' },
  pending:             { dot: 'var(--fg3)',           bg: 'var(--surface3)',       color: 'var(--fg3)' },
  waiting_for_service: { dot: 'var(--warning)',       bg: 'rgba(245,158,11,0.12)',color: '#fbbf24' },
};

function formatDay(dateStr: string): string {
  const d = new Date(dateStr);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  if (d.toDateString() === today.toDateString())     return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
}

function TimelineRow({ task, onClick }: { task: TaskListItem; onClick: () => void }) {
  const s = STATUS_STYLES[task.status] ?? STATUS_STYLES['pending'];
  const isProcessing = task.status === 'processing' || task.status === 'pending';
  const time = new Date(task.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

  return (
    <div
      onClick={onClick}
      className="flex items-center gap-4 px-5 py-3 cursor-pointer transition-colors"
      style={{ borderBottom: '1px solid var(--border)' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface2)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; }}
    >
      {/* Timeline dot */}
      <div className="flex flex-col items-center gap-1 flex-shrink-0">
        <span
          className={`w-2.5 h-2.5 rounded-full ${isProcessing ? 'animate-pulse' : ''}`}
          style={{ background: s.dot, boxShadow: isProcessing ? `0 0 6px ${s.dot}` : 'none' }}
        />
      </div>

      {/* Time */}
      <span className="w-12 text-[11px] font-mono flex-shrink-0" style={{ color: 'var(--fg3)' }}>
        {time}
      </span>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[13px] font-medium capitalize" style={{ color: 'var(--fg1)' }}>
            {task.platform} · {task.content_type}
          </span>
          <span
            className="text-[10.5px] font-semibold px-1.5 py-0.5 rounded"
            style={{ background: s.bg, color: s.color }}
          >
            {task.status}
          </span>
        </div>
        <div className="flex items-center gap-3 mt-0.5 flex-wrap">
          <span className="text-[11px] font-mono" style={{ color: 'var(--fg3)' }}>
            {task.task_id.slice(0, 8)}…
          </span>
          <span className="text-[11px]" style={{ color: 'var(--fg3)' }}>
            {task.items_completed}/{task.quantity} items
          </span>
          {task.total_cost_usd > 0 && (
            <span className="text-[11px] font-mono" style={{ color: 'var(--fg2)' }}>
              ${task.total_cost_usd.toFixed(2)}
            </span>
          )}
        </div>
      </div>

      <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--fg3)' }}>
        <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

export default function HistoryPage() {
  const router = useRouter();
  const { data: tasks, isLoading } = useAllTasks();

  const grouped = useMemo(() => {
    if (!tasks) return [];
    const sorted = [...tasks].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    const map = new Map<string, TaskListItem[]>();
    for (const task of sorted) {
      const day = new Date(task.created_at).toDateString();
      if (!map.has(day)) map.set(day, []);
      map.get(day)!.push(task);
    }
    return Array.from(map.entries()).map(([day, items]) => ({ day, label: formatDay(items[0].created_at), items }));
  }, [tasks]);

  return (
    <>
      <Topbar
        title="History"
        subtitle={tasks ? `${tasks.length} task${tasks.length !== 1 ? 's' : ''} total` : undefined}
      />

      <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 flex flex-col gap-6 max-w-3xl">
        {isLoading && (
          <div className="flex items-center gap-2 py-16 text-sm" style={{ color: 'var(--fg3)' }}>
            <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--accent-dim)', borderTopColor: 'var(--accent)' }} />
            Loading history…
          </div>
        )}

        {!isLoading && grouped.length === 0 && (
          <p className="py-16 text-center text-[13px]" style={{ color: 'var(--fg3)' }}>
            No tasks yet. Submit a brief on the New Task page.
          </p>
        )}

        {grouped.map(({ day, label, items }) => (
          <div key={day}>
            {/* Day header */}
            <div className="flex items-center gap-3 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--fg3)' }}>
                {label}
              </span>
              <div className="flex-1 h-px" style={{ background: 'var(--border)' }} />
              <span className="text-[10px] font-mono" style={{ color: 'var(--fg3)' }}>
                {items.length} task{items.length !== 1 ? 's' : ''}
              </span>
            </div>

            {/* Tasks for this day */}
            <div className="rounded-[var(--radius)] overflow-hidden" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
              {items.map((task) => (
                <TimelineRow
                  key={task.task_id}
                  task={task}
                  onClick={() => router.push(`/tasks/${task.task_id}`)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
