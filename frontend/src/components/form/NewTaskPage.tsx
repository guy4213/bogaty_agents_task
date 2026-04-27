'use client';

import { useState, useRef } from 'react';
import { Topbar } from '@/components/Topbar';
import { NewTaskForm } from './NewTaskForm';
import { EstimatePanel } from './EstimatePanel';
import { RecentTasksPanel } from './RecentTasksPanel';
import type { ContentType } from '@/types/api';

function GhostButton({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-[5px] text-[12px] font-medium px-3 py-[5px] rounded-[var(--radius-sm)] transition-colors whitespace-nowrap"
      style={{ border: '1px solid var(--border2)', color: 'var(--fg2)', fontFamily: 'var(--font)' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface2)'; (e.currentTarget as HTMLElement).style.color = 'var(--fg1)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--fg2)'; }}
    >
      {children}
    </button>
  );
}

export function NewTaskPage() {
  const [contentType, setContentType] = useState<ContentType>('comment');
  const [quantity, setQuantity] = useState(2);
  const [description, setDescription] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleImportBrief() {
    fileInputRef.current?.click();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      if (!text) return;

      if (file.name.endsWith('.json')) {
        try {
          const parsed = JSON.parse(text);
          // Support {description: "..."} or {brief: "..."} or plain string value
          const extracted =
            parsed.description ?? parsed.brief ?? parsed.text ?? parsed.content;
          setDescription(typeof extracted === 'string' ? extracted.slice(0, 2000) : text.slice(0, 2000));
        } catch {
          setDescription(text.slice(0, 2000));
        }
      } else {
        setDescription(text.slice(0, 2000));
      }
    };
    reader.readAsText(file);
    // Reset so the same file can be re-imported
    e.target.value = '';
  }

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept=".txt,.json"
        className="hidden"
        onChange={handleFileChange}
      />

      <Topbar
        title="New Task"
        subtitle="Submit a brief to generate platform-ready content."
        actions={
          <div className="hidden sm:flex items-center gap-2">
            <GhostButton onClick={handleImportBrief}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M6 1v5M6 6l2.5-2.5M6 6L3.5 3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                <path d="M1 8.5v1a1 1 0 001 1h8a1 1 0 001-1v-1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
              Import Brief
            </GhostButton>
            <GhostButton onClick={() => window.open('http://localhost:8000/docs', '_blank')}>
              Docs ↗
            </GhostButton>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="p-4 sm:p-6 lg:p-8 flex flex-col lg:flex-row gap-5 lg:gap-7 lg:items-start">
          <div className="w-full lg:w-[460px] lg:flex-none flex flex-col gap-5">
            <NewTaskForm
              contentType={contentType}
              setContentType={setContentType}
              quantity={quantity}
              setQuantity={setQuantity}
              description={description}
              setDescription={setDescription}
            />
          </div>

          <div className="w-full lg:flex-1 lg:min-w-0 flex flex-col gap-5">
            <EstimatePanel contentType={contentType} quantity={quantity} />
            <RecentTasksPanel />
          </div>
        </div>
      </div>
    </>
  );
}
