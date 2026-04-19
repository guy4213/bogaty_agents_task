import type { AssetRecord, CommentItem } from '@/types/api';
import { CommentCard } from './CommentCard';

interface CommentsGridProps {
  assets: AssetRecord[];
}

function extractComments(asset: AssetRecord): CommentItem[] {
  if (!asset.content) return [];

  const content = asset.content;

  if (Array.isArray(content)) {
    return content as CommentItem[];
  }

  if (typeof content === 'object' && content !== null) {
    const obj = content as Record<string, unknown>;
    if (Array.isArray(obj['comments'])) return obj['comments'] as CommentItem[];
    if (Array.isArray(obj['generated_texts'])) return obj['generated_texts'] as CommentItem[];
    if (Array.isArray(obj['items'])) return obj['items'] as CommentItem[];
    if (typeof obj['text'] === 'string') return [obj as unknown as CommentItem];
  }

  return [];
}

export function CommentsGrid({ assets }: CommentsGridProps) {
  const textAssets = assets.filter(
    (a) => a.asset_type === 'text' || a.file_format === 'json',
  );

  const allComments: { comment: CommentItem; validationPassed: boolean | null }[] = [];

  for (const asset of textAssets) {
    const comments = extractComments(asset);
    for (const c of comments) {
      allComments.push({ comment: c, validationPassed: asset.validation_passed });
    }
  }

  if (allComments.length === 0) {
    return (
      <p className="text-sm text-zinc-500 py-8 text-center">
        No comments to display.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {allComments.map(({ comment, validationPassed }, i) => (
        <CommentCard
          key={i}
          comment={comment}
          index={i}
          validationPassed={validationPassed}
        />
      ))}
    </div>
  );
}
