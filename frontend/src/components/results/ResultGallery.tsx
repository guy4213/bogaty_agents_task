import type { AssetRecord } from '@/types/api';
import { CommentsGrid } from './CommentsGrid';
import { PostsGrid } from './PostsGrid';
import { ReelsGrid } from './ReelsGrid';

interface ResultGalleryProps {
  contentType: string;
  assets: AssetRecord[];
  isProcessing: boolean;
}

export function ResultGallery({ contentType, assets, isProcessing }: ResultGalleryProps) {
  if (contentType === 'comment') {
    return <CommentsGrid assets={assets} />;
  }

  if (contentType === 'post') {
    return <PostsGrid assets={assets} aspect="1:1" />;
  }

  if (contentType === 'story') {
    return <PostsGrid assets={assets} aspect="9:16" />;
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
