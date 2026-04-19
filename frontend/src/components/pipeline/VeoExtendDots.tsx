interface VeoExtendDotsProps {
  completed: number;
  isProcessing?: boolean;
}

const LABELS = ['8s', '+7s', '+7s', '+7s'];

export function VeoExtendDots({ completed, isProcessing }: VeoExtendDotsProps) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-zinc-500 mr-1">Veo extends</span>
      {LABELS.map((label, i) => {
        const isDone = i < completed;
        const isActive = isProcessing && i === completed;

        return (
          <div key={i} className="flex flex-col items-center gap-0.5">
            <div
              className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold transition-colors ${
                isDone
                  ? 'bg-emerald-500 text-white'
                  : isActive
                    ? 'bg-indigo-400 text-white animate-pulse'
                    : 'bg-zinc-200 text-zinc-400'
              }`}
            >
              {isDone ? '✓' : isActive ? '⏳' : '○'}
            </div>
            <span className="text-[9px] text-zinc-400">{label}</span>
          </div>
        );
      })}
    </div>
  );
}
