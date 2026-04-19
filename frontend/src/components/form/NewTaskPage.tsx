'use client';

import { useState } from 'react';
import { Topbar } from '@/components/Topbar';
import { NewTaskForm } from './NewTaskForm';
import { EstimatePanel } from './EstimatePanel';
import { RecentTasksPanel } from './RecentTasksPanel';
import type { ContentType } from '@/types/api';

export function NewTaskPage() {
  const [contentType, setContentType] = useState<ContentType>('comment');
  const [quantity, setQuantity] = useState(10);

  return (
    <>
      <Topbar
        title="New Task"
        subtitle="Submit a brief to generate platform-ready content."
        actions={
          <>
            <button
              type="button"
              className="flex items-center gap-[5px] text-[12px] font-medium px-3 py-[5px] rounded-[var(--radius-sm)] transition-colors"
              style={{ border: '1px solid var(--border2)', color: 'var(--fg2)', fontFamily: 'var(--font)' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface2)'; (e.currentTarget as HTMLElement).style.color = 'var(--fg1)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--fg2)'; }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M6 1v5M6 6l2.5-2.5M6 6L3.5 3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                <path d="M1 8.5v1a1 1 0 001 1h8a1 1 0 001-1v-1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
              Import Brief
            </button>
            <button
              type="button"
              className="text-[12px] font-medium px-3 py-[5px] rounded-[var(--radius-sm)] transition-colors"
              style={{ border: '1px solid var(--border2)', color: 'var(--fg2)', fontFamily: 'var(--font)' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface2)'; (e.currentTarget as HTMLElement).style.color = 'var(--fg1)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--fg2)'; }}
            >
              Docs ↗
            </button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-8 flex gap-7 min-h-0">
        {/* Form column */}
        <div className="flex-none w-[460px] flex flex-col gap-5">
          <NewTaskForm
            contentType={contentType}
            setContentType={setContentType}
            quantity={quantity}
            setQuantity={setQuantity}
          />
        </div>

        {/* Right column */}
        <div className="flex-1 min-w-0 flex flex-col gap-5">
          <EstimatePanel contentType={contentType} quantity={quantity} />
          <RecentTasksPanel />
        </div>
      </div>
    </>
  );
}
