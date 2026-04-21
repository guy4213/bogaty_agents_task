'use client';

import Link from 'next/link';
import { useTask } from '@/hooks/useTask';
import { Topbar } from '@/components/Topbar';
import { PipelineStrip } from '@/components/pipeline/PipelineStrip';
import { MetricsLine } from '@/components/metrics/MetricsLine';
import { ResultGallery } from '@/components/results/ResultGallery';

const STATUS_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  pending:             { label: 'Pending',    color: 'var(--fg3)',        bg: 'var(--surface3)' },
  processing:          { label: 'Processing', color: 'var(--accent-light)', bg: 'var(--accent-dim)' },
  completed:           { label: 'Completed',  color: '#4ade80',           bg: 'rgba(34,197,94,0.1)' },
  partial:             { label: 'Partial',    color: '#fbbf24',           bg: 'rgba(245,158,11,0.1)' },
  failed:              { label: 'Failed',     color: '#f87171',           bg: 'rgba(239,68,68,0.1)' },
  waiting_for_service: { label: 'Waiting',    color: '#fbbf24',           bg: 'rgba(245,158,11,0.1)' },
};

interface PageProps {
  params: { taskId: string };
}

export default function TaskDetailPage({ params }: PageProps) {
  const { taskId } = params;
  const { status: statusQuery, content: contentQuery, isLoading } = useTask(taskId);

  if (isLoading) {
    return (
      <>
        <Topbar title="Task Detail" subtitle="Loading…" />
        <div className="flex-1 flex items-center justify-center">
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--fg3)' }}>
            <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--accent-dim)', borderTopColor: 'var(--accent)' }} />
            Loading task…
          </div>
        </div>
      </>
    );
  }

  if (statusQuery.isError || !statusQuery.data) {
    return (
      <>
        <Topbar title="Task Detail" subtitle="Not found" />
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          <p className="font-medium" style={{ color: 'var(--danger)' }}>Task not found</p>
          <p className="text-sm font-mono" style={{ color: 'var(--fg3)' }}>{taskId}</p>
          <Link href="/" className="text-sm mt-2" style={{ color: 'var(--accent-light)' }}>
            ← New task
          </Link>
        </div>
      </>
    );
  }

  const task = statusQuery.data;
  const content = contentQuery.data;
  const badge = STATUS_BADGE[task.status] ?? STATUS_BADGE['pending'];
  const isProcessing = task.status === 'processing' || task.status === 'pending';

  return (
    <>
      <Topbar
        title={`${task.platform.charAt(0).toUpperCase() + task.platform.slice(1)} · ${task.content_type}`}
        subtitle={task.task_id}
        actions={
          <Link href="/" className="text-[12px] font-medium px-3 py-[5px] rounded-[var(--radius-sm)] transition-colors" style={{ border: '1px solid var(--border2)', color: 'var(--fg2)' }}>
            ← New task
          </Link>
        }
      />

      <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 space-y-8">
        {/* Status badge */}
        <div className="flex items-center gap-3">
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[12px] font-semibold"
            style={{ background: badge.bg, color: badge.color }}
          >
            {isProcessing && (
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
            )}
            {badge.label}
          </span>
          <span className="text-[11px] font-mono" style={{ color: 'var(--fg3)' }}>
            {task.task_id}
          </span>
        </div>

        {/* Description */}
        {task.description && (
          <section>
            <p className="text-[10px] font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--fg3)' }}>
              Brief
            </p>
            <p className="text-[13px] leading-relaxed" style={{ color: 'var(--fg2)' }}>
              {task.description}
            </p>
          </section>
        )}

        {/* Pipeline */}
        <section>
          <p className="text-[10px] font-semibold uppercase tracking-widest mb-3" style={{ color: 'var(--fg3)' }}>
            Pipeline
          </p>
          <PipelineStrip task={task} />
        </section>

        {/* Metrics */}
        <section>
          <p className="text-[10px] font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--fg3)' }}>
            Progress
          </p>
          <MetricsLine task={task} />
        </section>

        {/* Errors */}
        {task.errors.length > 0 && (
          <section>
            <p className="text-[10px] font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--fg3)' }}>
              Errors
            </p>
            <ul className="space-y-1">
              {task.errors.map((err, i) => (
                <li
                  key={i}
                  className="text-[11px] font-mono px-3 py-1.5 rounded-[var(--radius-sm)]"
                  style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--danger)', border: '1px solid rgba(239,68,68,0.15)' }}
                >
                  {err}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Results */}
        {content && content.assets && content.assets.length > 0 && (
          <section>
            <p className="text-[10px] font-semibold uppercase tracking-widest mb-4" style={{ color: 'var(--fg3)' }}>
              Results
            </p>
            <ResultGallery
              contentType={task.content_type}
              platform={task.platform}
              assets={content.assets}
              isProcessing={isProcessing}
            />
          </section>
        )}

        {isProcessing && (!content || !content.assets || content.assets.length === 0) && (
          <div className="flex items-center gap-2 py-4 text-sm" style={{ color: 'var(--fg3)' }}>
            <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--accent-dim)', borderTopColor: 'var(--accent)' }} />
            Waiting for results…
          </div>
        )}
      </div>
    </>
  );
}
