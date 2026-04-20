'use client';

import { useMemo } from 'react';
import { Topbar } from '@/components/Topbar';
import { useAllTasks } from '@/hooks/useAllTasks';
import type { ContentType, Platform } from '@/types/api';

const CONTENT_TYPES: ContentType[] = ['comment', 'post', 'story', 'reels'];
const PLATFORMS: Platform[]        = ['instagram', 'tiktok', 'twitter', 'telegram', 'facebook'];

interface Breakdown { label: string; cost: number; items: number; tasks: number; }

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-[var(--radius)] p-5 flex flex-col gap-1" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
      <span className="text-[11px] font-medium" style={{ color: 'var(--fg3)' }}>{label}</span>
      <span className="text-[26px] font-bold font-mono tracking-tight" style={{ color: 'var(--fg1)', letterSpacing: '-0.02em' }}>{value}</span>
      {sub && <span className="text-[11px]" style={{ color: 'var(--fg3)' }}>{sub}</span>}
    </div>
  );
}

function BreakdownTable({ title, rows, maxCost }: { title: string; rows: Breakdown[]; maxCost: number }) {
  return (
    <div className="rounded-[var(--radius)] overflow-hidden" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
      <div className="px-5 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <span className="text-[13px] font-semibold" style={{ color: 'var(--fg1)' }}>{title}</span>
      </div>
      <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
        {rows.length === 0 ? (
          <p className="px-5 py-8 text-[13px] text-center" style={{ color: 'var(--fg3)' }}>No data yet.</p>
        ) : rows.map((row) => (
          <div key={row.label} className="flex items-center gap-4 px-5 py-3" style={{ borderColor: 'var(--border)' }}>
            <span className="w-24 text-[13px] font-medium capitalize flex-shrink-0" style={{ color: 'var(--fg1)' }}>
              {row.label}
            </span>
            {/* Bar */}
            <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--surface3)' }}>
              <div
                className="h-full rounded-full"
                style={{ width: maxCost > 0 ? `${(row.cost / maxCost) * 100}%` : '0%', background: 'var(--accent)' }}
              />
            </div>
            <span className="w-14 text-right text-[12px] font-mono flex-shrink-0" style={{ color: 'var(--fg1)' }}>
              {row.cost > 0 ? `$${row.cost.toFixed(2)}` : '—'}
            </span>
            <span className="w-16 text-right text-[11px] font-mono flex-shrink-0" style={{ color: 'var(--fg3)' }}>
              {row.items} items
            </span>
            <span className="w-14 text-right text-[11px] font-mono flex-shrink-0" style={{ color: 'var(--fg3)' }}>
              {row.tasks} task{row.tasks !== 1 ? 's' : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function UsagePage() {
  const { data: tasks, isLoading } = useAllTasks();

  const stats = useMemo(() => {
    if (!tasks || tasks.length === 0) return null;

    const totalCost    = tasks.reduce((s, t) => s + t.total_cost_usd, 0);
    const totalItems   = tasks.reduce((s, t) => s + t.items_completed, 0);
    const completedCnt = tasks.filter((t) => t.status === 'completed' || t.status === 'partial').length;
    const avgCost      = completedCnt > 0 ? totalCost / completedCnt : 0;

    const byType: Breakdown[] = CONTENT_TYPES.map((ct) => {
      const subset = tasks.filter((t) => t.content_type === ct);
      return {
        label: ct,
        cost:  subset.reduce((s, t) => s + t.total_cost_usd, 0),
        items: subset.reduce((s, t) => s + t.items_completed, 0),
        tasks: subset.length,
      };
    }).filter((r) => r.tasks > 0).sort((a, b) => b.cost - a.cost);

    const byPlatform: Breakdown[] = PLATFORMS.map((p) => {
      const subset = tasks.filter((t) => t.platform === p);
      return {
        label: p,
        cost:  subset.reduce((s, t) => s + t.total_cost_usd, 0),
        items: subset.reduce((s, t) => s + t.items_completed, 0),
        tasks: subset.length,
      };
    }).filter((r) => r.tasks > 0).sort((a, b) => b.cost - a.cost);

    return { totalCost, totalItems, totalTasks: tasks.length, avgCost, byType, byPlatform };
  }, [tasks]);

  return (
    <>
      <Topbar title="Usage & Cost" subtitle="Aggregated from all tasks in this session." />

      <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 flex flex-col gap-6">
        {isLoading && (
          <div className="flex items-center gap-2 py-16 text-sm" style={{ color: 'var(--fg3)' }}>
            <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--accent-dim)', borderTopColor: 'var(--accent)' }} />
            Loading…
          </div>
        )}

        {!isLoading && !stats && (
          <p className="py-16 text-center text-[13px]" style={{ color: 'var(--fg3)' }}>
            No tasks yet. Submit a brief on the New Task page.
          </p>
        )}

        {stats && (
          <>
            {/* Summary row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <StatCard label="Total Cost" value={`$${stats.totalCost.toFixed(2)}`} sub="all tasks" />
              <StatCard label="Items Generated" value={stats.totalItems.toLocaleString()} sub="delivered" />
              <StatCard label="Tasks" value={String(stats.totalTasks)} sub="all time" />
              <StatCard label="Avg Cost / Task" value={`$${stats.avgCost.toFixed(2)}`} sub="completed only" />
            </div>

            {/* By content type */}
            <BreakdownTable
              title="By Content Type"
              rows={stats.byType}
              maxCost={Math.max(...stats.byType.map((r) => r.cost), 0.01)}
            />

            {/* By platform */}
            <BreakdownTable
              title="By Platform"
              rows={stats.byPlatform}
              maxCost={Math.max(...stats.byPlatform.map((r) => r.cost), 0.01)}
            />
          </>
        )}
      </div>
    </>
  );
}
