import type { AssetRecord } from '@/types/api';
import { PostCard } from './PostCard';

interface PostsGridProps {
  assets: AssetRecord[];
  aspect: '1:1' | '9:16';
}

interface ItemGroup {
  itemIndex: number;
  imageAsset: AssetRecord | undefined;
  captionAsset: AssetRecord | undefined;
}

function groupByItem(assets: AssetRecord[]): ItemGroup[] {
  const map = new Map<number, ItemGroup>();

  for (const asset of assets) {
    const idx = asset.item_index;
    if (!map.has(idx)) {
      map.set(idx, { itemIndex: idx, imageAsset: undefined, captionAsset: undefined });
    }
    const group = map.get(idx)!;

    if (asset.asset_type === 'image' || asset.file_format === 'png') {
      group.imageAsset = asset;
    } else if (
      asset.asset_type === 'text' ||
      asset.asset_type === 'caption' ||
      asset.file_format === 'json' ||
      asset.file_format === 'txt'
    ) {
      group.captionAsset = asset;
    }
  }

  return Array.from(map.values()).sort((a, b) => a.itemIndex - b.itemIndex);
}

export function PostsGrid({ assets, aspect }: PostsGridProps) {
  const groups = groupByItem(assets);

  if (groups.length === 0) {
    return (
      <p className="text-sm text-zinc-500 py-8 text-center">
        No posts to display.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {groups.map((group, i) => (
        <PostCard
          key={group.itemIndex}
          itemIndex={group.itemIndex}
          imageAsset={group.imageAsset}
          captionAsset={group.captionAsset}
          aspect={aspect}
          isAnchor={i === 0}
        />
      ))}
    </div>
  );
}
