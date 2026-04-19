'use client';

import { use } from 'react';
import Link from 'next/link';
import { useTask } from '@/hooks/useTask';
import { PipelineStrip } from '@/components/pipeline/PipelineStrip';
import { MetricsLine } from '@/components/metrics/MetricsLine';
import { ResultGallery } from '@/components/results/ResultGallery';

const STATUS_BADGE: Record<string, { label: string; classes: string }> = {
  pending: {
    label: 'Pending',
    classes: 'bg-zinc-100 text-zinc-600',
  },
  processing: {
    label: 'Processing',
    classes: 'bg-indigo-100 text-indigo-700',
  },
  completed: {
    label: 'Completed',
    classes: 'bg-emerald-100 text-emerald-700',
  },
  partial: {
    label: 'Partial',
    classes: 'bg-amber-100 text-amber-700',
  },
  failed: {
    label: 'Failed',
    classes: 'bg-rose-100 text-rose-700',
  },
  waiting_for_service: {
    label: 'Waiting',
    classes: 'bg-amber-100 text-amber-700',
  },
};

interface PageProps {
  params: Promise<{ taskId: string }>;
}

export default function TaskDetailPage({ params }: PageProps) {
  const { taskId } = use(params);
  const { status: statusQuery, content: contentQuery, isLoading } = useTask(taskId);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500 py-16">
        <div className="w-4 h-4 border-2 border-indigo-300 border-t-indigo-600 rounded-full animate-spin" />
        Loading task…
      </div>
    );
  }

  if (statusQuery.isError || !statusQuery.data) {
    return (
      <div className="py-16 text-center">
        <p className="text-rose-600 font-medium mb-2">Task not found</p>
        <p className="text-sm text-zinc-500 mb-4">
          Task <span className="font-mono">{taskId}</span> could not be loaded.
        </p>
        <Link href="/" className="text-sm text-indigo-600 hover:text-indigo-800">
          ← New task
        </Link>
      </div>
    );
  }

  const task = statusQuery.data;
  const content = contentQuery.data;
  const badge = STATUS_BADGE[task.status] ?? STATUS_BADGE['pending'];
  const isProcessing =
    task.status === 'processing' || task.status === 'pending';

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-xl font-semibold text-zinc-900 capitalize">
              {task.platform} · {task.content_type}
            </h1>
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.classes}`}
            >
              {isProcessing && (
                <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse" />
              )}
              {badge.label}
            </span>
          </div>
          <p className="text-xs text-zinc-400 font-mono">{task.task_id}</p>
        </div>

        <Link
          href="/"
          className="text-sm text-indigo-600 hover:text-indigo-800 mt-1"
        >
          ← New task
        </Link>
      </div>

      {/* Pipeline */}
      <section>
        <h2 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">
          Pipeline
        </h2>
        <PipelineStrip task={task} />
      </section>

      {/* Metrics */}
      <section>
        <h2 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">
          Progress
        </h2>
        <MetricsLine task={task} />
      </section>

      {/* Errors */}
      {task.errors.length > 0 && (
        <section>
          <h2 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">
            Errors
          </h2>
          <ul className="space-y-1">
            {task.errors.map((err, i) => (
              <li
                key={i}
                className="text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded px-3 py-1.5 font-mono"
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
          <h2 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-4">
            Results
          </h2>
          <ResultGallery
            contentType={task.content_type}
            assets={content.assets}
            isProcessing={isProcessing}
          />
        </section>
      )}

      {isProcessing && (!content || !content.assets || content.assets.length === 0) && (
        <div className="flex items-center gap-2 text-sm text-zinc-500 py-4">
          <div className="w-4 h-4 border-2 border-indigo-300 border-t-indigo-600 rounded-full animate-spin" />
          Waiting for results…
        </div>
      )}
    </div>
  );
}
