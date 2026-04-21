import type { AssetRecord } from '@/types/api';
import { ReelCard } from './ReelCard';

interface ReelsGridProps { assets: AssetRecord[]; isProcessing: boolean; }
interface ReelGroup { itemIndex: number; videoAsset: AssetRecord | undefined; textAsset: AssetRecord | undefined; }

function groupReels(assets: AssetRecord[]): ReelGroup[] {
  const map = new Map<number, ReelGroup>();
  for (const asset of assets) {
    const idx = asset.item_index;
    if (!map.has(idx)) map.set(idx, { itemIndex: idx, videoAsset: undefined, textAsset: undefined });
    const group = map.get(idx)!;
    if (asset.asset_type === 'video' || asset.file_format === 'mp4') {
      group.videoAsset = asset;
    } else if (asset.asset_type === 'text' || asset.file_format === 'json' || asset.file_format === 'txt') {
      group.textAsset = asset;
    }
  }
  return Array.from(map.values()).sort((a, b) => a.itemIndex - b.itemIndex);
}

export function ReelsGrid({ assets, isProcessing }: ReelsGridProps) {
  const groups = groupReels(assets);
  if (groups.length === 0) {
    return (
      <p className="py-8 text-sm text-center" style={{ color: 'var(--fg3)' }}>
        {isProcessing ? 'Generating reels…' : 'No reels to display.'}
      </p>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {groups.map((group) => (
        <ReelCard
          key={group.itemIndex}
          itemIndex={group.itemIndex}
          videoAsset={group.videoAsset}
          textAsset={group.textAsset}
          completedExtends={group.videoAsset ? 4 : 0}
          isProcessing={isProcessing && !group.videoAsset}
        />
      ))}
    </div>
  );
}
