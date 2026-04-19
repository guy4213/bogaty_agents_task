import type { ContentType } from '@/types/api';

interface EstimatePanelProps {
  contentType: ContentType;
  quantity: number;
}

const CONCURRENCY: Record<ContentType, number> = {
  comment: 48,
  post: 18,
  story: 18,
  reels: 8,
};

const TIME_PER_ITEM: Record<ContentType, number> = {
  comment: 0.08,
  post: 1,
  story: 1,
  reels: 10,
};

const COST_PER_ITEM: Record<ContentType, number> = {
  comment: 0.001,
  post: 0.07,
  story: 0.07,
  reels: 1.5,
};

function formatTime(minutes: number): string {
  if (minutes < 1) return `~${Math.max(1, Math.round(minutes * 60))}s`;
  if (minutes < 60) return `~${Math.round(minutes)}m`;
  return `~${(minutes / 60).toFixed(1)}h`;
}

export function EstimatePanel({ contentType, quantity }: EstimatePanelProps) {
  const concurrency = CONCURRENCY[contentType];
  const totalMin = (quantity * TIME_PER_ITEM[contentType]) / concurrency;
  const cost = (quantity * COST_PER_ITEM[contentType]).toFixed(2);
  const timeStr = formatTime(totalMin);

  const cells = [
    { label: 'Est. Cost', value: `$${cost}`, sub: `for ${quantity} item${quantity !== 1 ? 's' : ''}` },
    { label: 'Est. Time', value: timeStr, sub: 'wall clock' },
    { label: 'Parallel', value: String(concurrency), sub: 'concurrency' },
  ];

  return (
    <div
      className="rounded-[var(--radius)] overflow-hidden"
      style={{ border: '1px solid var(--border)' }}
    >
      <div
        className="px-5 py-3 flex items-center gap-2"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5" style={{ color: 'var(--accent-light)' }}>
          <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.3" />
          <path d="M7 4.5v5M5.5 6h2.5a1 1 0 010 2H5.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
        <span className="text-[13px] font-semibold" style={{ color: 'var(--fg1)' }}>
          Estimated Cost
        </span>
      </div>
      <div
        className="grid"
        style={{
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 1,
          background: 'var(--border)',
        }}
      >
        {cells.map((cell) => (
          <div
            key={cell.label}
            className="flex flex-col gap-1 px-4 py-3.5"
            style={{ background: 'var(--surface2)' }}
          >
            <span className="text-[11px] font-medium" style={{ color: 'var(--fg3)' }}>
              {cell.label}
            </span>
            <span
              className="text-[18px] font-bold tracking-tight font-mono"
              style={{ color: 'var(--fg1)', letterSpacing: '-0.02em' }}
            >
              {cell.value}
            </span>
            <span className="text-[10px]" style={{ color: 'var(--fg3)' }}>
              {cell.sub}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
