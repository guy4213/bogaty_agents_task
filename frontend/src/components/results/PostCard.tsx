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
  aspect: '1:1' | '9:16';
  isAnchor: boolean;
}

function extractCaption(asset: AssetRecord | undefined): { text: string; hashtags: string[] } {
  if (!asset?.content) return { text: '', hashtags: [] };

  const content = asset.content;

  if (typeof content === 'string') {
    return { text: content, hashtags: [] };
  }

  if (typeof content === 'object' && content !== null) {
    const obj = content as Record<string, unknown>;
    const text =
      (typeof obj['text'] === 'string' ? obj['text'] : '') ||
      (typeof obj['caption'] === 'string' ? obj['caption'] : '');
    const hashtags = Array.isArray(obj['hashtags'])
      ? (obj['hashtags'] as string[])
      : [];
    return { text, hashtags };
  }

  return { text: '', hashtags: [] };
}

export function PostCard({ itemIndex, imageAsset, captionAsset, aspect, isAnchor }: PostCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { text, hashtags } = extractCaption(captionAsset);
  const imageUrl = imageAsset?.download_url ?? null;
  const rtl = text ? isHebrew(text) : false;
  const aspectClass = aspect === '9:16' ? 'aspect-[9/16]' : 'aspect-square';

  return (
    <div className="bg-white border border-zinc-200 rounded-xl overflow-hidden hover:border-zinc-300 transition-colors">
      <div className={`relative ${aspectClass} bg-zinc-100`}>
        {imageUrl ? (
          <Image
            src={imageUrl}
            alt={`Item ${itemIndex}`}
            fill
            unoptimized
            className="object-cover"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-zinc-400 text-sm">
            No image
          </div>
        )}
        {isAnchor && <StyleAnchorBadge />}
        {imageUrl && (
          <a
            href={imageUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="absolute bottom-2 right-2 bg-white/90 backdrop-blur-sm text-xs px-2 py-1 rounded shadow-sm border border-zinc-200 text-zinc-700 hover:bg-white transition-colors"
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
                className={`text-sm text-zinc-800 leading-relaxed ${
                  expanded ? '' : 'line-clamp-4'
                }`}
              >
                {text}
              </p>
              {text.length > 200 && (
                <button
                  type="button"
                  onClick={() => setExpanded((e) => !e)}
                  className="text-xs text-indigo-600 hover:text-indigo-800 mt-1"
                >
                  {expanded ? 'show less' : 'read more'}
                </button>
              )}
            </div>
          )}

          {hashtags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {hashtags.map((tag) => (
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
      )}
    </div>
  );
}
