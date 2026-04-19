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
    <div className="bg-white border border-zinc-200 rounded-xl overflow-hidden hover:border-zinc-300 transition-colors">
      <div className="relative aspect-[9/16] bg-zinc-900 max-h-[600px] mx-auto" style={{ maxHeight: 600 }}>
        {videoUrl ? (
          <video
            controls
            className="w-full h-full object-contain"
            src={videoUrl}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-zinc-500 text-sm">
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
            className="text-xs text-indigo-600 hover:text-indigo-800 inline-flex items-center gap-1"
          >
            Download video ↗
          </a>
        )}
      </div>
    </div>
  );
}
