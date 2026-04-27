'use client';

import { useState } from 'react';
import { isHebrew } from '@/lib/rtl';
import type { CommentItem } from '@/types/api';

interface CommentCardProps {
  comment: CommentItem;
  index: number;
  validationPassed?: boolean | null;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text)
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })
      .catch(() => {});
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      className="text-[11px] px-2 py-0.5 rounded transition-colors shrink-0"
      style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: copied ? 'var(--success)' : 'var(--fg3)' }}
    >
      {copied ? '✓' : 'Copy'}
    </button>
  );
}

export function CommentCard({ comment, index, validationPassed }: CommentCardProps) {
  const rtl = isHebrew(comment.text);

  return (
    <div
      className="flex flex-col gap-2 p-4 rounded-[var(--radius)] transition-colors"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border2)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {comment.persona && (
            <span
              className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium truncate max-w-[130px]"
              style={{ background: 'var(--surface2)', color: 'var(--fg2)', border: '1px solid var(--border2)' }}
            >
              {comment.persona}
            </span>
          )}
        </div>
        <span className="text-[11px] font-mono shrink-0" style={{ color: 'var(--fg3)' }}>
          #{index + 1}
        </span>
      </div>

      <p dir={rtl ? 'rtl' : 'ltr'} className="text-[13px] leading-relaxed" style={{ color: 'var(--fg1)' }}>
        {comment.text}
      </p>

      <div className="flex items-center justify-between mt-1 gap-2">
        {validationPassed !== null && validationPassed !== undefined ? (
          <span
            className="text-[11px] font-medium flex items-center gap-1"
            style={{ color: validationPassed ? 'var(--success)' : 'var(--danger)' }}
          >
            {validationPassed ? '✓ passed' : '✗ failed'}
          </span>
        ) : <span />}

        <div className={`flex items-center gap-2 ${rtl ? 'flex-row-reverse' : ''}`}>
          {comment.hashtags && comment.hashtags.length > 0 && (
            <div className={`flex flex-wrap gap-1 ${rtl ? 'flex-row-reverse' : ''}`}>
              {comment.hashtags.slice(0, 3).map((tag) => (
                <span
                  key={tag}
                  className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{ background: 'var(--accent-dim)', color: 'var(--accent-light)' }}
                >
                  #{tag.replace(/^#/, '')}
                </span>
              ))}
            </div>
          )}
          <CopyButton text={comment.text} />
        </div>
      </div>
    </div>
  );
}
