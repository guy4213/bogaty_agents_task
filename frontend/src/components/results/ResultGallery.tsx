import type { AssetRecord } from '@/types/api';
import { CommentsGrid } from './CommentsGrid';
import { PostsGrid } from './PostsGrid';
import { ReelsGrid } from './ReelsGrid';

type Aspect = '1:1' | '9:16' | '16:9';

function resolveAspect(contentType: string, platform: string): Aspect {
  if (contentType === 'story' || contentType === 'reels') return '9:16';
  if (contentType === 'post') {
    if (platform === 'twitter' || platform === 'facebook') return '16:9';
  }
  return '1:1';
}

interface ResultGalleryProps {
  contentType: string;
  platform: string;
  assets: AssetRecord[];
  isProcessing: boolean;
}

export function ResultGallery({ contentType, platform, assets, isProcessing }: ResultGalleryProps) {
  if (contentType === 'comment') {
    return <CommentsGrid assets={assets} />;
  }

  if (contentType === 'post' || contentType === 'story') {
    return <PostsGrid assets={assets} aspect={resolveAspect(contentType, platform)} />;
  }

  if (contentType === 'reels') {
    return <ReelsGrid assets={assets} isProcessing={isProcessing} />;
  }

  return (
    <p className="text-sm text-zinc-500 py-8 text-center">
      Unknown content type: {contentType}
    </p>
  );
}
