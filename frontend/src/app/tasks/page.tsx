'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { Topbar } from '@/components/Topbar';
import { useAllTasks } from '@/hooks/useAllTasks';
import type { TaskListItem, TaskStatus, ContentType, Platform } from '@/types/api';

const STATUS_STYLES: Record<string, { dot: string; bg: string; color: string }> = {
  completed:           { dot: 'var(--success)',       bg: 'rgba(34,197,94,0.1)',    color: '#4ade80' },
  processing:          { dot: 'var(--accent-light)',  bg: 'rgba(99,102,241,0.12)',  color: 'var(--accent-light)' },
  partial:             { dot: 'var(--warning)',        bg: 'rgba(245,158,11,0.12)', color: '#fbbf24' },
  failed:              { dot: 'var(--danger)',         bg: 'rgba(239,68,68,0.1)',   color: '#f87171' },
  pending:             { dot: 'var(--fg3)',            bg: 'var(--surface3)',        color: 'var(--fg3)' },
  waiting_for_service: { dot: 'var(--warning)',        bg: 'rgba(245,158,11,0.12)', color: '#fbbf24' },
};

const ALL_STATUSES: TaskStatus[] = ['pending', 'processing', 'completed', 'partial', 'failed'];
const ALL_TYPES: ContentType[]   = ['comment', 'post', 'story', 'reels'];
const ALL_PLATFORMS: Platform[]  = ['instagram', 'tiktok', 'twitter', 'telegram', 'facebook'];

function FilterPill({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="px-2.5 py-1 rounded-full text-[11px] font-medium transition-all capitalize"
      style={{
        background: active ? 'var(--accent-dim)' : 'var(--surface2)',
        border: `1px solid ${active ? 'var(--accent-border)' : 'var(--border)'}`,
        color: active ? 'var(--accent-light)' : 'var(--fg3)',
      }}
    >
      {label}
    </button>
  );
}

function TaskRow({ task, onClick }: { task: TaskListItem; onClick: () => void }) {
  const s = STATUS_STYLES[task.status] ?? STATUS_STYLES['pending'];
  const isProcessing = task.status === 'processing' || task.status === 'pending';
  const progress = task.quantity > 0 ? (task.items_completed / task.quantity) * 100 : 0;

  return (
    <tr
      onClick={onClick}
      className="cursor-pointer transition-colors"
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface2)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; }}
    >
      {/* Status */}
      <td className="px-4 py-3 whitespace-nowrap">
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full flex-shrink-0 ${isProcessing ? 'animate-pulse' : ''}`}
            style={{ background: s.dot, boxShadow: isProcessing ? `0 0 5px ${s.dot}` : 'none' }}
          />
          <span
            className="px-1.5 py-0.5 rounded text-[10.5px] font-semibold"
            style={{ background: s.bg, color: s.color }}
          >
            {task.status}
          </span>
        </div>
      </td>

      {/* ID */}
      <td className="px-4 py-3">
        <span className="text-[12px] font-mono" style={{ color: 'var(--fg2)' }}>
          {task.task_id.slice(0, 8)}…
        </span>
      </td>

      {/* Platform · Type */}
      <td className="px-4 py-3 whitespace-nowrap">
        <span className="text-[13px] font-medium capitalize" style={{ color: 'var(--fg1)' }}>
          {task.platform}
        </span>
        <span className="text-[11px] ml-1.5" style={{ color: 'var(--fg3)' }}>
          {task.content_type}
        </span>
      </td>

      {/* Progress */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="w-20 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--surface3)' }}>
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${progress}%`,
                background: task.status === 'failed' ? 'var(--danger)' : task.status === 'partial' ? 'var(--warning)' : 'var(--success)',
              }}
            />
          </div>
          <span className="text-[11px] font-mono" style={{ color: 'var(--fg3)' }}>
            {task.items_completed}/{task.quantity}
          </span>
        </div>
      </td>

      {/* Cost */}
      <td className="px-4 py-3 whitespace-nowrap text-right">
        <span className="text-[12px] font-mono" style={{ color: task.total_cost_usd > 0 ? 'var(--fg1)' : 'var(--fg3)' }}>
          {task.total_cost_usd > 0 ? `$${task.total_cost_usd.toFixed(2)}` : '—'}
        </span>
      </td>

      {/* Date */}
      <td className="px-4 py-3 whitespace-nowrap text-right">
        <span className="text-[11px] font-mono" style={{ color: 'var(--fg3)' }}>
          {new Date(task.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
        </span>
      </td>
    </tr>
  );
}

export default function AllTasksPage() {
  const router = useRouter();
  const { data: tasks, isLoading, refetch } = useAllTasks();
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter]     = useState<string>('all');
  const [platformFilter, setPlatformFilter] = useState<string>('all');

  const filtered = useMemo(() => {
    if (!tasks) return [];
    return [...tasks]
      .filter((t) => statusFilter === 'all'   || t.status       === statusFilter)
      .filter((t) => typeFilter   === 'all'   || t.content_type === typeFilter)
      .filter((t) => platformFilter === 'all' || t.platform     === platformFilter)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }, [tasks, statusFilter, typeFilter, platformFilter]);

  return (
    <>
      <Topbar
        title="All Tasks"
        subtitle={tasks ? `${tasks.length} task${tasks.length !== 1 ? 's' : ''}` : undefined}
        actions={
          <button
            type="button"
            onClick={() => refetch()}
            className="flex items-center gap-1.5 text-[12px] font-medium px-3 py-[5px] rounded-[var(--radius-sm)] transition-colors"
            style={{ border: '1px solid var(--border2)', color: 'var(--fg2)' }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface2)'; (e.currentTarget as HTMLElement).style.color = 'var(--fg1)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--fg2)'; }}
          >
            <svg viewBox="0 0 14 14" fill="none" className="w-3 h-3">
              <path d="M12 7A5 5 0 112 7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
              <path d="M12 3v4h-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Refresh
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 flex flex-col gap-4">
        {/* Filters */}
        <div className="flex flex-wrap gap-3">
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-semibold uppercase tracking-wider mr-1" style={{ color: 'var(--fg3)' }}>Status</span>
            <FilterPill label="all" active={statusFilter === 'all'} onClick={() => setStatusFilter('all')} />
            {ALL_STATUSES.map((s) => (
              <FilterPill key={s} label={s} active={statusFilter === s} onClick={() => setStatusFilter(s)} />
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-semibold uppercase tracking-wider mr-1" style={{ color: 'var(--fg3)' }}>Type</span>
            <FilterPill label="all" active={typeFilter === 'all'} onClick={() => setTypeFilter('all')} />
            {ALL_TYPES.map((t) => (
              <FilterPill key={t} label={t} active={typeFilter === t} onClick={() => setTypeFilter(t)} />
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] font-semibold uppercase tracking-wider mr-1" style={{ color: 'var(--fg3)' }}>Platform</span>
            <FilterPill label="all" active={platformFilter === 'all'} onClick={() => setPlatformFilter('all')} />
            {ALL_PLATFORMS.map((p) => (
              <FilterPill key={p} label={p} active={platformFilter === p} onClick={() => setPlatformFilter(p)} />
            ))}
          </div>
        </div>

        {/* Table */}
        <div className="rounded-[var(--radius)] overflow-hidden" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          {isLoading ? (
            <div className="flex items-center justify-center py-16 gap-2" style={{ color: 'var(--fg3)' }}>
              <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--accent-dim)', borderTopColor: 'var(--accent)' }} />
              Loading tasks…
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-16 text-center text-[13px]" style={{ color: 'var(--fg3)' }}>
              {tasks?.length === 0 ? 'No tasks yet. Submit a brief on the New Task page.' : 'No tasks match the current filters.'}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Status', 'Task ID', 'Platform / Type', 'Progress', 'Cost', 'Created'].map((h, i) => (
                      <th
                        key={h}
                        className={`px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider ${i >= 4 ? 'text-right' : 'text-left'}`}
                        style={{ color: 'var(--fg3)' }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((task) => (
                    <TaskRow
                      key={task.task_id}
                      task={task}
                      onClick={() => router.push(`/tasks/${task.task_id}`)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
