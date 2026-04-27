'use client';

import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Unhandled error:', error);
  }, [error]);

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8">
      <p className="text-[15px] font-semibold" style={{ color: 'var(--danger)' }}>
        Something went wrong
      </p>
      <p className="text-[13px] font-mono text-center max-w-md" style={{ color: 'var(--fg3)' }}>
        {error.message || 'An unexpected error occurred.'}
      </p>
      <button
        type="button"
        onClick={reset}
        className="text-[13px] font-medium px-4 py-2 rounded-[var(--radius-sm)] transition-colors"
        style={{ border: '1px solid var(--border2)', color: 'var(--fg2)', background: 'var(--surface2)' }}
      >
        Try again
      </button>
    </div>
  );
}
