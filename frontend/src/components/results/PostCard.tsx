'use client';

import Image from 'next/image';
import { useState } from 'react';
import { isHebrew } from '@/lib/rtl';
import { StyleAnchorBadge } from './StyleAnchorBadge';
import type { AssetRecord } from '@/types/api';

interface PostCardProps {
  itemIndex: number;
  imageAsset: AssetRecord | undefined;
  captionAsset: AssetRecord | undefined;
  aspect: '1:1' | '9:16' | '16:9';
  isAnchor: boolean;
}

function extractCaption(asset: AssetRecord | undefined): { text: string; hashtags: string[] } {
  if (!asset?.content) return { text: '', hashtags: [] };
  const content = asset.content;
  if (typeof content === 'string') return { text: content, hashtags: [] };
  const obj = (Array.isArray(content) ? content[0] : content) as Record<string, unknown> | null;
  if (obj && typeof obj === 'object') {
    const text = (typeof obj['text'] === 'string' ? obj['text'] : '') || (typeof obj['caption'] === 'string' ? obj['caption'] : '');
    const hashtags = Array.isArray(obj['hashtags']) ? (obj['hashtags'] as string[]) : [];
    return { text, hashtags };
  }
  return { text: '', hashtags: [] };
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
      className="text-[11px] px-2 py-0.5 rounded transition-colors"
      style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: copied ? 'var(--success)' : 'var(--fg3)' }}
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}

export function PostCard({ itemIndex, imageAsset, captionAsset, aspect, isAnchor }: PostCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { text, hashtags } = extractCaption(captionAsset);
  const imageUrl = imageAsset?.download_url ?? null;
  const rtl = text ? isHebrew(text) : false;
  const aspectClass = aspect === '9:16' ? 'aspect-[9/16]' : aspect === '16:9' ? 'aspect-video' : 'aspect-square';
  const copyText = [text, ...hashtags.map((h) => `#${h.replace(/^#/, '')}`)].filter(Boolean).join('\n');

  return (
    <div
      className="rounded-[var(--radius)] overflow-hidden transition-colors"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border2)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; }}
    >
      <div className={`relative ${aspectClass}`} style={{ background: 'var(--surface3)' }}>
        {imageUrl ? (
          <Image src={imageUrl} alt={`Item ${itemIndex}`} fill unoptimized className="object-cover" />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-[13px]" style={{ color: 'var(--fg3)' }}>
            No image
          </div>
        )}
        {isAnchor && <StyleAnchorBadge />}
        {imageUrl && (
          <a
            href={imageUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="absolute bottom-2 right-2 text-[11px] px-2 py-1 rounded transition-colors"
            style={{ background: 'rgba(15,17,23,0.85)', backdropFilter: 'blur(4px)', border: '1px solid var(--border2)', color: 'var(--fg2)' }}
          >
            Download
          </a>
        )}
      </div>

      {(text || hashtags.length > 0) && (
        <div className="p-3 space-y-2">
          {text && (
            <div>
              <p
                dir={rtl ? 'rtl' : 'ltr'}
                className={`text-[13px] leading-relaxed ${expanded ? '' : 'line-clamp-4'}`}
                style={{ color: 'var(--fg1)' }}
              >
                {text}
              </p>
              {text.length > 100 && (
                <button
                  type="button"
                  onClick={() => setExpanded((e) => !e)}
                  className="text-[11px] mt-1 transition-colors"
                  style={{ color: 'var(--accent-light)' }}
                >
                  {expanded ? 'show less' : 'read more'}
                </button>
              )}
            </div>
          )}
          {hashtags.length > 0 && (
            <div className={`flex flex-wrap gap-1 ${rtl ? 'flex-row-reverse' : ''}`}>
              {hashtags.map((tag) => (
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
          {copyText && (
            <div className={`flex ${rtl ? 'justify-start' : 'justify-end'}`}>
              <CopyButton text={copyText} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
