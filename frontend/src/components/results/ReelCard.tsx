'use client';

import { useState } from 'react';
import { VeoExtendDots } from '@/components/pipeline/VeoExtendDots';
import { isHebrew } from '@/lib/rtl';
import type { AssetRecord } from '@/types/api';

interface ReelCardProps {
  itemIndex: number;
  videoAsset: AssetRecord | undefined;
  textAsset: AssetRecord | undefined;
  completedExtends: number;
  isProcessing: boolean;
}

function extractReelText(asset: AssetRecord | undefined): { caption: string; hashtags: string[] } {
  if (!asset?.content) return { caption: '', hashtags: [] };
  const raw = asset.content;
  const script = (Array.isArray(raw) ? raw[0] : raw) as Record<string, unknown> | null;
  if (!script || typeof script !== 'object') return { caption: '', hashtags: [] };
  const caption =
    (typeof script['full_caption'] === 'string' ? script['full_caption'] : '') ||
    (typeof script['text'] === 'string' ? script['text'] : '');
  const hashtags = Array.isArray(script['hashtags']) ? (script['hashtags'] as string[]) : [];
  return { caption, hashtags };
}

export function ReelCard({ itemIndex, videoAsset, textAsset, completedExtends, isProcessing }: ReelCardProps) {
  const [expanded, setExpanded] = useState(false);
  const videoUrl = videoAsset?.download_url ?? null;
  const { caption, hashtags } = extractReelText(textAsset);
  const rtl = caption ? isHebrew(caption) : false;

  return (
    <div
      className="mx-auto w-full max-w-[280px] rounded-[var(--radius)] overflow-hidden transition-colors"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border2)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; }}
    >
      {/* 9:16 video player — width-constrained so container matches video exactly */}
      <div className="relative aspect-[9/16]" style={{ background: '#000' }}>
        {videoUrl ? (
          <video controls className="w-full h-full object-cover" src={videoUrl} />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-[13px]" style={{ color: 'var(--fg3)' }}>
            {isProcessing ? 'Generating video…' : `No video for item ${itemIndex}`}
          </div>
        )}
      </div>

      {/* Meta: extend progress + download */}
      <div className="px-3 pt-3 flex items-center justify-between">
        <VeoExtendDots completed={completedExtends} isProcessing={isProcessing} />
        {videoUrl && (
          <a
            href={videoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px]"
            style={{ color: 'var(--accent-light)' }}
          >
            Download ↗
          </a>
        )}
      </div>

      {/* Caption + hashtags */}
      {(caption || hashtags.length > 0) && (
        <div className="px-3 pb-3 pt-2 space-y-2">
          {caption && (
            <div>
              <p
                dir={rtl ? 'rtl' : 'ltr'}
                className={`text-[13px] leading-relaxed ${expanded ? '' : 'line-clamp-4'}`}
                style={{ color: 'var(--fg1)' }}
              >
                {caption}
              </p>
              {caption.length > 100 && (
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
            <div className="flex flex-wrap gap-1">
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
        </div>
      )}
    </div>
  );
}
