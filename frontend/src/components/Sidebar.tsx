'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useHealth } from '@/hooks/useHealth';

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

interface NavItem {
  label: string;
  href: string;
  badge?: string;
  icon: React.ReactNode;
}

const WORKSPACE_NAV: NavItem[] = [
  {
    label: 'New Task',
    href: '/',
    icon: (
      <svg viewBox="0 0 15 15" fill="none" className="w-[15px] h-[15px]">
        <path d="M2 3h11M2 7.5h11M2 12h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    label: 'All Tasks',
    href: '/tasks',
    icon: (
      <svg viewBox="0 0 15 15" fill="none" className="w-[15px] h-[15px]">
        <rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
        <rect x="8" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
        <rect x="2" y="8" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
        <rect x="8" y="8" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      </svg>
    ),
  },
  {
    label: 'Health',
    href: '/health-check',
    icon: (
      <svg viewBox="0 0 15 15" fill="none" className="w-[15px] h-[15px]">
        <path d="M7.5 1v2M13.5 7.5h-2M7.5 12v2M3.5 3.5l1.5 1.5M10 10l1.5 1.5M1 7.5h2M10 5l1.5-1.5M5 10l-1.5 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
    ),
  },
];

const ANALYTICS_NAV: NavItem[] = [
  {
    label: 'Usage & Cost',
    href: '/usage',
    icon: (
      <svg viewBox="0 0 15 15" fill="none" className="w-[15px] h-[15px]">
        <path d="M2 12l3.5-4 2.5 2.5L11 6l2 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    label: 'History',
    href: '/history',
    icon: (
      <svg viewBox="0 0 15 15" fill="none" className="w-[15px] h-[15px]">
        <circle cx="7.5" cy="7.5" r="5.5" stroke="currentColor" strokeWidth="1.3" />
        <path d="M7.5 5v3l1.5 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
    ),
  },
];

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const style: React.CSSProperties = active
    ? { background: 'var(--accent-dim)', color: 'var(--accent-light)' }
    : {};

  return (
    <Link
      href={item.href}
      className="flex items-center gap-[9px] px-[10px] py-2 rounded-[var(--radius-sm)] text-[13.5px] font-[450] transition-colors duration-150 group"
      style={{
        color: active ? 'var(--accent-light)' : 'var(--fg2)',
        fontWeight: active ? 500 : undefined,
        ...style,
      }}
      onMouseEnter={(e) => {
        if (!active) {
          (e.currentTarget as HTMLElement).style.background = 'var(--surface2)';
          (e.currentTarget as HTMLElement).style.color = 'var(--fg1)';
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          (e.currentTarget as HTMLElement).style.background = '';
          (e.currentTarget as HTMLElement).style.color = 'var(--fg2)';
        }
      }}
    >
      <span style={{ opacity: active ? 1 : 0.7 }}>{item.icon}</span>
      {item.label}
      {item.badge && (
        <span
          className="ml-auto text-[10px] font-semibold font-mono px-[6px] py-[1px] rounded-full border"
          style={{
            background: 'var(--surface3)',
            color: 'var(--fg3)',
            borderColor: 'var(--border2)',
          }}
        >
          {item.badge}
        </span>
      )}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { data: health, allHealthy } = useHealth();

  const healthState =
    !health ? 'unknown' :
    health.overall === 'healthy' ? 'healthy' :
    health.overall === 'down' ? 'down' : 'degraded';

  const healthLabel =
    !health ? 'Checking…' :
    allHealthy ? 'All systems healthy' :
    health.services.filter((s) => s.status === 'down').length > 0
      ? `${health.services.filter((s) => s.status === 'down').length} service${health.services.filter((s) => s.status === 'down').length > 1 ? 's' : ''} down`
      : '1 service degraded';

  const dotColor =
    healthState === 'healthy' ? 'var(--success)' :
    healthState === 'down' ? 'var(--danger)' : 'var(--warning)';

  return (
    <nav
      className="flex-shrink-0 flex flex-col h-screen sticky top-0"
      style={{
        width: 220,
        background: 'var(--surface)',
        borderRight: '1px solid var(--border)',
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center gap-[10px] px-[18px] py-5"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div
          className="w-[30px] h-[30px] rounded-lg grid place-items-center flex-shrink-0"
          style={{ background: 'var(--accent)' }}
        >
          <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4">
            <path d="M2 4h3v3H2zM6.5 4h3v3h-3zM11 4h3v3h-3zM2 9h3v3H2zM6.5 9h3v3h-3z" fill="white" opacity="0.9" />
            <path d="M11 9l2.5 1.5-2.5 1.5V9z" fill="white" opacity="0.9" />
          </svg>
        </div>
        <span
          className="text-[14px] font-semibold tracking-tight"
          style={{ color: 'var(--fg1)' }}
        >
          Content Engine
        </span>
      </div>

      {/* Nav */}
      <div className="flex-1 px-[10px] py-3 space-y-0.5">
        <p
          className="text-[10px] font-semibold uppercase tracking-[0.08em] px-2 py-2"
          style={{ color: 'var(--fg3)' }}
        >
          Workspace
        </p>
        {WORKSPACE_NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            active={
              item.href === '/'
                ? pathname === '/'
                : pathname.startsWith(item.href)
            }
          />
        ))}

        <p
          className="text-[10px] font-semibold uppercase tracking-[0.08em] px-2 pt-4 pb-2"
          style={{ color: 'var(--fg3)' }}
        >
          Analytics
        </p>
        {ANALYTICS_NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            active={pathname.startsWith(item.href)}
          />
        ))}
      </div>

      {/* Health badge */}
      <div className="px-[10px] py-[14px]" style={{ borderTop: '1px solid var(--border)' }}>
        <button
          type="button"
          onClick={() => window.open(`${BASE_URL}/health`, '_blank')}
          className="w-full flex items-center gap-[7px] px-[10px] py-2 rounded-[var(--radius-sm)] transition-colors text-left"
          style={{
            background: 'var(--surface2)',
            border: '1px solid var(--border)',
          }}
        >
          <span
            className="w-[7px] h-[7px] rounded-full flex-shrink-0"
            style={{
              background: dotColor,
              boxShadow: healthState !== 'unknown' ? `0 0 6px ${dotColor}` : 'none',
            }}
          />
          <span className="text-[12px] font-medium flex-1" style={{ color: 'var(--fg2)' }}>
            {healthLabel}
          </span>
          <span style={{ color: 'var(--fg3)', fontSize: 10 }}>›</span>
        </button>
      </div>
    </nav>
  );
}
