'use client';

import { useSidebar } from '@/providers/SidebarContext';

interface TopbarProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export function Topbar({ title, subtitle, actions }: TopbarProps) {
  const { toggleMobile } = useSidebar();

  return (
    <div
      className="h-[52px] flex items-center px-4 md:px-7 gap-3 flex-shrink-0"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      {/* Hamburger — mobile only */}
      <button
        type="button"
        onClick={toggleMobile}
        className="md:hidden flex-shrink-0 w-8 h-8 flex flex-col justify-center items-center gap-[5px]"
        aria-label="Toggle menu"
      >
        <span className="block w-5 h-px rounded" style={{ background: 'var(--fg2)' }} />
        <span className="block w-5 h-px rounded" style={{ background: 'var(--fg2)' }} />
        <span className="block w-5 h-px rounded" style={{ background: 'var(--fg2)' }} />
      </button>

      <span className="text-[14px] font-semibold flex-shrink-0" style={{ color: 'var(--fg1)' }}>
        {title}
      </span>
      {subtitle && (
        <span className="text-[12.5px] flex-1 truncate hidden sm:block" style={{ color: 'var(--fg3)' }}>
          {subtitle}
        </span>
      )}
      {actions && (
        <div className="flex items-center gap-2 ml-auto flex-shrink-0">
          {actions}
        </div>
      )}
    </div>
  );
}
