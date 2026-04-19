import { isHebrew } from '@/lib/rtl';
import type { CommentItem } from '@/types/api';

interface CommentCardProps {
  comment: CommentItem;
  index: number;
  validationPassed?: boolean | null;
}

export function CommentCard({ comment, index, validationPassed }: CommentCardProps) {
  const rtl = isHebrew(comment.text);

  return (
    <div className="bg-white border border-zinc-200 rounded-xl p-4 flex flex-col gap-2 hover:border-zinc-300 transition-colors">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {comment.persona && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-zinc-100 text-zinc-600 truncate max-w-[120px]">
              {comment.persona}
            </span>
          )}
        </div>
        <span className="text-xs text-zinc-400 font-mono shrink-0">#{index + 1}</span>
      </div>

      <p
        dir={rtl ? 'rtl' : 'ltr'}
        className="text-sm text-zinc-800 leading-relaxed"
      >
        {comment.text}
      </p>

      <div className="flex items-center justify-between mt-1">
        {validationPassed !== null && validationPassed !== undefined ? (
          <span
            className={`text-xs font-medium flex items-center gap-1 ${
              validationPassed ? 'text-emerald-600' : 'text-rose-600'
            }`}
          >
            {validationPassed ? '✓ passed' : '✗ failed'}
          </span>
        ) : (
          <span />
        )}

        {comment.hashtags && comment.hashtags.length > 0 && (
          <div className="flex flex-wrap gap-1 justify-end">
            {comment.hashtags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="text-[10px] text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded"
              >
                #{tag.replace(/^#/, '')}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
