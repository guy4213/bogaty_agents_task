'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRecentTasks } from '@/hooks/useRecentTasks';

const STATUS_COLOR: Record<string, string> = {
  completed: 'text-emerald-600',
  partial: 'text-amber-600',
  failed: 'text-rose-600',
  processing: 'text-indigo-600',
  pending: 'text-zinc-500',
  waiting_for_service: 'text-amber-600',
};

export function RecentTasksDropdown() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const { data: tasks } = useRecentTasks();

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-sm text-zinc-600 hover:text-zinc-900 px-2 py-1 rounded hover:bg-zinc-100 transition-colors"
      >
        Recent
        <svg
          className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-80 bg-white border border-zinc-200 rounded-lg shadow-lg z-50">
          {!tasks || tasks.length === 0 ? (
            <p className="px-4 py-3 text-sm text-zinc-500">No tasks yet.</p>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {tasks.map((t) => (
                <li key={t.task_id}>
                  <button
                    type="button"
                    className="w-full text-left px-4 py-3 hover:bg-zinc-50 transition-colors"
                    onClick={() => {
                      router.push(`/tasks/${t.task_id}`);
                      setOpen(false);
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-zinc-800 capitalize">
                        {t.platform} · {t.content_type}
                      </span>
                      <span
                        className={`text-xs font-medium ${STATUS_COLOR[t.status] ?? 'text-zinc-500'}`}
                      >
                        {t.status}
                      </span>
                    </div>
                    <div className="text-xs text-zinc-400 mt-0.5 font-mono">
                      {t.task_id.slice(0, 8)}… · qty {t.quantity}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
