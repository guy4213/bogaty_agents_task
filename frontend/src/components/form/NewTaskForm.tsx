'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { generateTask } from '@/lib/api';
import type { Platform, ContentType, Language } from '@/types/api';

const MAX_QUANTITY: Record<ContentType, number> = {
  comment: 200,
  post: 50,
  story: 50,
  reels: 50,
};

const PLATFORMS: { value: Platform; label: string; icon: React.ReactNode }[] = [
  {
    value: 'instagram',
    label: 'Instagram',
    icon: (
      <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5">
        <rect x="2" y="2" width="10" height="10" rx="3" stroke="currentColor" strokeWidth="1.3" />
        <circle cx="7" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.2" />
        <circle cx="10" cy="4" r="0.6" fill="currentColor" />
      </svg>
    ),
  },
  {
    value: 'tiktok',
    label: 'TikTok',
    icon: (
      <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5">
        <path d="M9 1H7v8a2 2 0 11-2-2V5a4 4 0 104 4V5a5 5 0 003 1V4a3 3 0 01-3-3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    value: 'twitter',
    label: 'X / Twitter',
    icon: (
      <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5">
        <path d="M1.5 1.5l11 11M12.5 1.5l-11 11" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    value: 'telegram',
    label: 'Telegram',
    icon: (
      <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5">
        <path d="M12.5 2L1 6l4.5 1.5L7 12l2-3 3.5 2.5L12.5 2z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    value: 'facebook',
    label: 'Facebook',
    icon: (
      <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5">
        <path d="M9 1H7.5A2.5 2.5 0 005 3.5V5H3v2.5h2V13h2.5V7.5H9L9.5 5H7.5V3.5c0-.3.2-.5.5-.5H9V1z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      </svg>
    ),
  },
];

const CONTENT_TYPES: { value: ContentType; label: string; icon: string }[] = [
  { value: 'comment', label: 'Comment', icon: '💬' },
  { value: 'post', label: 'Post', icon: '🖼' },
  { value: 'story', label: 'Story', icon: '⬛' },
  { value: 'reels', label: 'Reels', icon: '🎬' },
];

const QTY_PRESETS = [5, 10, 25, 50];

interface PipelineBarProps {
  contentType: ContentType;
}

function PipelineBar({ contentType }: PipelineBarProps) {
  const showImage = contentType === 'post' || contentType === 'story' || contentType === 'reels';
  const showVideo = contentType === 'reels';

  const steps = [
    { label: 'Content', active: true },
    { label: 'Image', active: showImage },
    { label: 'Video', active: showVideo },
    { label: 'Validate', active: true },
  ];

  return (
    <div
      className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-[var(--radius-sm)]"
      style={{ background: 'var(--surface2)', border: '1px solid var(--border)' }}
    >
      {steps.map((step, i) => (
        <span key={step.label} className="flex items-center gap-1.5">
          {i > 0 && (
            <span className="text-[10px] opacity-50" style={{ color: 'var(--fg3)' }}>
              →
            </span>
          )}
          <span className="flex items-center gap-[5px]">
            <span
              className="w-[5px] h-[5px] rounded-full"
              style={
                step.active
                  ? { background: 'var(--accent-light)' }
                  : { background: 'var(--surface3)', border: '1px solid var(--border2)' }
              }
            />
            <span
              className="text-[10.5px] font-medium"
              style={{ color: step.active ? 'var(--accent-light)' : 'var(--fg3)' }}
            >
              {step.label}
            </span>
          </span>
        </span>
      ))}
    </div>
  );
}

interface NewTaskFormProps {
  contentType: ContentType;
  setContentType: (v: ContentType) => void;
  quantity: number;
  setQuantity: (v: number) => void;
}

export function NewTaskForm({ contentType, setContentType, quantity, setQuantity }: NewTaskFormProps) {
  const router = useRouter();
  const [platform, setPlatform] = useState<Platform>('instagram');
  const [language, setLanguage] = useState<Language>('en');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const maxQty = MAX_QUANTITY[contentType];

  function handleContentTypeChange(ct: ContentType) {
    setContentType(ct);
    if (quantity > MAX_QUANTITY[ct]) setQuantity(MAX_QUANTITY[ct]);
  }

  function adjustQty(delta: number) {
    const next = Math.max(1, Math.min(maxQty, quantity + delta));
    setQuantity(next);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!description.trim()) {
      const el = document.getElementById('desc-field') as HTMLTextAreaElement;
      if (el) { el.style.borderColor = 'var(--danger)'; setTimeout(() => { el.style.borderColor = ''; }, 1500); el.focus(); }
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const res = await generateTask({ platform, content_type: contentType, language, quantity, description });
      router.push(`/tasks/${res.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed');
      setSubmitting(false);
    }
  }

  return (
    <div
      className="rounded-[var(--radius)] overflow-hidden"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
    >
      {/* Card header */}
      <div
        className="px-5 py-4 flex items-center"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5" style={{ color: 'var(--accent-light)' }}>
            <rect x="1" y="1" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.3" />
            <path d="M4 7h6M4 4.5h3M4 9.5h4.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          <span className="text-[13px] font-semibold" style={{ color: 'var(--fg1)' }}>
            Task Configuration
          </span>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="p-5 flex flex-col gap-5">
        {/* Platform */}
        <div className="flex flex-col gap-2">
          <span className="text-[12px] font-semibold" style={{ color: 'var(--fg2)' }}>
            Platform
          </span>
          <div className="grid grid-cols-5 gap-1.5">
            {PLATFORMS.map((p) => {
              const isActive = platform === p.value;
              return (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setPlatform(p.value)}
                  className="flex flex-col items-center gap-[5px] px-1.5 py-2.5 rounded-[var(--radius-sm)] text-[10px] font-medium transition-all duration-150"
                  style={{
                    background: isActive ? 'var(--accent-dim)' : 'var(--surface2)',
                    border: `1px solid ${isActive ? 'var(--accent)' : 'var(--border)'}`,
                    color: isActive ? 'var(--accent-light)' : 'var(--fg3)',
                  }}
                >
                  <span
                    className="w-[26px] h-[26px] rounded-[6px] grid place-items-center"
                    style={{ background: isActive ? 'rgba(99,102,241,0.18)' : 'var(--surface3)' }}
                  >
                    {p.icon}
                  </span>
                  <span>{p.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Content Type */}
        <div className="flex flex-col gap-2">
          <span className="text-[12px] font-semibold" style={{ color: 'var(--fg2)' }}>
            Content Type
          </span>
          <div
            className="grid grid-cols-4 gap-1 p-[3px] rounded-[var(--radius-sm)]"
            style={{ background: 'var(--surface2)', border: '1px solid var(--border)' }}
          >
            {CONTENT_TYPES.map((ct) => {
              const isActive = contentType === ct.value;
              return (
                <button
                  key={ct.value}
                  type="button"
                  onClick={() => handleContentTypeChange(ct.value)}
                  className="flex flex-col items-center gap-[3px] py-[7px] px-1 rounded-[5px] text-[12px] font-medium transition-all duration-150"
                  style={{
                    background: isActive ? 'var(--surface)' : 'transparent',
                    color: isActive ? 'var(--fg1)' : 'var(--fg3)',
                    boxShadow: isActive ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
                  }}
                >
                  <span className="text-[14px] leading-none">{ct.icon}</span>
                  <span>{ct.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Pipeline */}
        <PipelineBar contentType={contentType} />

        {/* Language */}
        <div className="flex flex-col gap-2">
          <span className="text-[12px] font-semibold" style={{ color: 'var(--fg2)' }}>
            Language
          </span>
          <div
            className="flex gap-[3px] p-[3px] rounded-[var(--radius-sm)] w-fit"
            style={{ background: 'var(--surface2)', border: '1px solid var(--border)' }}
          >
            {([['en', 'EN'], ['he', 'עב']] as [Language, string][]).map(([val, lbl]) => (
              <button
                key={val}
                type="button"
                onClick={() => setLanguage(val)}
                className="px-[18px] py-[6px] rounded-[5px] text-[12.5px] font-semibold tracking-wide transition-all duration-150"
                style={{
                  background: language === val ? 'var(--surface)' : 'transparent',
                  color: language === val ? 'var(--fg1)' : 'var(--fg3)',
                  boxShadow: language === val ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
                  fontSize: val === 'he' ? 13 : undefined,
                }}
              >
                {lbl}
              </button>
            ))}
          </div>
        </div>

        {/* Quantity */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[12px] font-semibold" style={{ color: 'var(--fg2)' }}>
              Quantity
            </span>
            <span className="text-[11px]" style={{ color: 'var(--fg3)' }}>
              max {maxQty}
            </span>
          </div>
          <div className="flex items-center gap-2.5 flex-wrap">
            <div
              className="flex items-center overflow-hidden w-fit"
              style={{ border: '1px solid var(--border2)', borderRadius: 'var(--radius-sm)', background: 'var(--surface2)' }}
            >
              <button
                type="button"
                onClick={() => adjustQty(-1)}
                className="w-[34px] h-[34px] grid place-items-center text-base transition-colors"
                style={{ color: 'var(--fg2)' }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface3)'; (e.currentTarget as HTMLElement).style.color = 'var(--fg1)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--fg2)'; }}
              >
                −
              </button>
              <input
                type="number"
                value={quantity}
                min={1}
                max={maxQty}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (!isNaN(v)) setQuantity(Math.max(1, Math.min(maxQty, v)));
                }}
                className="w-16 h-[34px] text-center text-[14px] font-semibold font-mono outline-none bg-transparent"
                style={{
                  borderLeft: '1px solid var(--border)',
                  borderRight: '1px solid var(--border)',
                  color: 'var(--fg1)',
                }}
              />
              <button
                type="button"
                onClick={() => adjustQty(1)}
                className="w-[34px] h-[34px] grid place-items-center text-base transition-colors"
                style={{ color: 'var(--fg2)' }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface3)'; (e.currentTarget as HTMLElement).style.color = 'var(--fg1)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--fg2)'; }}
              >
                +
              </button>
            </div>
            <div className="flex gap-[5px] flex-wrap">
              {QTY_PRESETS.filter((p) => p <= maxQty).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setQuantity(Math.min(p, maxQty))}
                  className="px-2 py-[3px] text-[11px] font-semibold font-mono rounded transition-all duration-150"
                  style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--fg3)' }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.borderColor = 'var(--accent-border)';
                    (e.currentTarget as HTMLElement).style.color = 'var(--accent-light)';
                    (e.currentTarget as HTMLElement).style.background = 'var(--accent-dim)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)';
                    (e.currentTarget as HTMLElement).style.color = 'var(--fg3)';
                    (e.currentTarget as HTMLElement).style.background = 'var(--surface2)';
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Description */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[12px] font-semibold" style={{ color: 'var(--fg2)' }}>
              Description
            </span>
            <span className="text-[11px] font-mono" style={{ color: 'var(--fg3)' }}>
              {description.length} / 2000
            </span>
          </div>
          <textarea
            id="desc-field"
            dir={language === 'he' ? 'rtl' : 'ltr'}
            value={description}
            onChange={(e) => setDescription(e.target.value.slice(0, 2000))}
            rows={4}
            placeholder={
              language === 'he'
                ? 'תיאור הבריף — נושא, טון, קהל יעד, נקודות מפתח…'
                : 'Describe the content brief — topic, tone, audience, key points…'
            }
            className="w-full rounded-[var(--radius-sm)] text-[13px] leading-relaxed px-3.5 py-3 resize-none outline-none transition-colors duration-150"
            style={{
              background: 'var(--surface2)',
              border: '1px solid var(--border2)',
              color: 'var(--fg1)',
              fontFamily: 'var(--font)',
            }}
            onFocus={(e) => { (e.target as HTMLElement).style.borderColor = 'var(--accent-border)'; }}
            onBlur={(e) => { (e.target as HTMLElement).style.borderColor = 'var(--border2)'; }}
            required
            minLength={5}
          />
        </div>

        {error && (
          <p
            className="text-[12px] px-3 py-2 rounded-[var(--radius-sm)] font-mono"
            style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--danger)', border: '1px solid rgba(239,68,68,0.2)' }}
          >
            {error}
          </p>
        )}

        {/* Generate */}
        <button
          type="submit"
          disabled={submitting || description.length < 5}
          className="w-full flex items-center justify-center gap-2 py-3.5 rounded-[var(--radius-sm)] text-[14px] font-semibold tracking-tight text-white transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ background: 'var(--accent)', fontFamily: 'var(--font)' }}
          onMouseEnter={(e) => {
            if (!(e.currentTarget as HTMLButtonElement).disabled) {
              (e.currentTarget as HTMLElement).style.background = '#5254cc';
              (e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)';
              (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 20px rgba(99,102,241,0.35)';
            }
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.background = 'var(--accent)';
            (e.currentTarget as HTMLElement).style.transform = '';
            (e.currentTarget as HTMLElement).style.boxShadow = '';
          }}
        >
          <svg viewBox="0 0 15 15" fill="none" className="w-[15px] h-[15px]">
            <path d="M7.5 1L9.5 6h5L10.5 9l2 5L7.5 11 3 14l2-5L1 6h5L7.5 1z" fill="currentColor" opacity="0.9" />
          </svg>
          {submitting ? 'Submitting…' : 'Generate Content'}
        </button>
      </form>
    </div>
  );
}
