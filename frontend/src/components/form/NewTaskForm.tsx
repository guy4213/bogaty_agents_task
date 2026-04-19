'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { generateTask } from '@/lib/api';
import type { Platform, ContentType, Language } from '@/types/api';

const PLATFORMS: Platform[] = ['instagram', 'tiktok', 'twitter', 'telegram', 'facebook'];
const CONTENT_TYPES: { value: ContentType; label: string }[] = [
  { value: 'comment', label: 'Comment' },
  { value: 'post', label: 'Post' },
  { value: 'story', label: 'Story' },
  { value: 'reels', label: 'Reels' },
];
const MAX_QUANTITY: Record<ContentType, number> = {
  comment: 200,
  post: 50,
  story: 50,
  reels: 50,
};

export function NewTaskForm() {
  const router = useRouter();

  const [platform, setPlatform] = useState<Platform>('instagram');
  const [contentType, setContentType] = useState<ContentType>('comment');
  const [language, setLanguage] = useState<Language>('en');
  const [quantity, setQuantity] = useState(1);
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const maxQty = MAX_QUANTITY[contentType];

  function handleContentTypeChange(ct: ContentType) {
    setContentType(ct);
    const max = MAX_QUANTITY[ct];
    if (quantity > max) setQuantity(max);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const res = await generateTask({
        platform,
        content_type: contentType,
        language,
        quantity,
        description,
      });
      router.push(`/tasks/${res.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed');
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Platform */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 mb-1.5">
          Platform
        </label>
        <select
          value={platform}
          onChange={(e) => setPlatform(e.target.value as Platform)}
          className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm text-zinc-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent capitalize"
        >
          {PLATFORMS.map((p) => (
            <option key={p} value={p} className="capitalize">
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </option>
          ))}
        </select>
      </div>

      {/* Content Type */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 mb-1.5">
          Content Type
        </label>
        <div className="flex rounded-lg border border-zinc-300 overflow-hidden">
          {CONTENT_TYPES.map(({ value, label }, i) => (
            <button
              key={value}
              type="button"
              onClick={() => handleContentTypeChange(value)}
              className={`flex-1 py-2 text-sm font-medium transition-colors ${
                i > 0 ? 'border-l border-zinc-300' : ''
              } ${
                contentType === value
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-zinc-600 hover:bg-zinc-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Language */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 mb-1.5">
          Language
        </label>
        <div className="flex rounded-lg border border-zinc-300 overflow-hidden w-fit">
          <button
            type="button"
            onClick={() => setLanguage('en')}
            className={`px-5 py-2 text-sm font-medium transition-colors ${
              language === 'en'
                ? 'bg-indigo-600 text-white'
                : 'bg-white text-zinc-600 hover:bg-zinc-50'
            }`}
          >
            EN
          </button>
          <button
            type="button"
            onClick={() => setLanguage('he')}
            className={`px-5 py-2 text-sm font-medium border-l border-zinc-300 transition-colors ${
              language === 'he'
                ? 'bg-indigo-600 text-white'
                : 'bg-white text-zinc-600 hover:bg-zinc-50'
            }`}
          >
            עב
          </button>
        </div>
      </div>

      {/* Quantity */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 mb-1.5">
          Quantity
          <span className="text-zinc-400 font-normal ml-1">(max {maxQty})</span>
        </label>
        <input
          type="number"
          min={1}
          max={maxQty}
          value={quantity}
          onChange={(e) =>
            setQuantity(Math.min(maxQty, Math.max(1, parseInt(e.target.value, 10) || 1)))
          }
          className="w-32 border border-zinc-300 rounded-lg px-3 py-2 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
      </div>

      {/* Description */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 mb-1.5">
          Description
          <span className="text-zinc-400 font-normal ml-1">
            ({description.length}/2000)
          </span>
        </label>
        <textarea
          dir={language === 'he' ? 'rtl' : 'ltr'}
          value={description}
          onChange={(e) => setDescription(e.target.value.slice(0, 2000))}
          rows={4}
          placeholder={
            language === 'he'
              ? 'תיאור התוכן שברצונך ליצור…'
              : 'Describe the content you want to generate…'
          }
          className="w-full border border-zinc-300 rounded-lg px-3 py-2 text-sm text-zinc-900 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          required
          minLength={5}
        />
      </div>

      {error && (
        <p className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting || description.length < 5}
        className="w-full sm:w-auto px-6 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
      >
        {submitting ? 'Submitting…' : 'Generate'}
      </button>
    </form>
  );
}
