interface VeoExtendDotsProps {
  completed: number;
  isProcessing?: boolean;
  totalClips?: number;
  clipDuration?: number;
}

export function VeoExtendDots({ completed, isProcessing, totalClips = 3, clipDuration = 10 }: VeoExtendDotsProps) {
  const labels = Array.from({ length: totalClips }, (_, i) =>
    i === 0 ? `${clipDuration}s` : `+${clipDuration}s`
  );

  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px]" style={{ color: 'var(--fg3)' }}>Clips</span>
      {labels.map((label, i) => {
        const isDone   = i < completed;
        const isActive = isProcessing && i === completed;
        return (
          <div key={i} className="flex flex-col items-center gap-0.5">
            <div
              className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold ${isActive ? 'animate-pulse' : ''}`}
              style={
                isDone   ? { background: 'var(--success)', color: '#fff' } :
                isActive ? { background: 'var(--accent)',  color: '#fff' } :
                           { background: 'var(--surface3)',color: 'var(--fg3)' }
              }
            >
              {isDone ? '✓' : isActive ? '⏳' : '○'}
            </div>
            <span className="text-[9px]" style={{ color: 'var(--fg3)' }}>{label}</span>
          </div>
        );
      })}
    </div>
  );
}
