import { VeoExtendDots } from '@/components/pipeline/VeoExtendDots';
import type { AssetRecord } from '@/types/api';

interface ReelCardProps {
  itemIndex: number;
  videoAsset: AssetRecord | undefined;
  completedExtends: number;
  isProcessing: boolean;
}

export function ReelCard({ itemIndex, videoAsset, completedExtends, isProcessing }: ReelCardProps) {
  const videoUrl = videoAsset?.download_url ?? null;

  return (
    <div
      className="rounded-[var(--radius)] overflow-hidden transition-colors"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border2)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; }}
    >
      <div className="relative aspect-[9/16] max-h-[600px]" style={{ background: '#000' }}>
        {videoUrl ? (
          <video controls className="w-full h-full object-contain" src={videoUrl} />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-[13px]" style={{ color: 'var(--fg3)' }}>
            {isProcessing ? 'Generating video…' : `No video for item ${itemIndex}`}
          </div>
        )}
      </div>
      <div className="p-3 space-y-2">
        <VeoExtendDots completed={completedExtends} isProcessing={isProcessing} />
        {videoUrl && (
          <a
            href={videoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] inline-flex items-center gap-1"
            style={{ color: 'var(--accent-light)' }}
          >
            Download video ↗
          </a>
        )}
      </div>
    </div>
  );
}
