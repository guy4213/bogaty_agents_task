import Link from 'next/link';
import { HealthDot } from './HealthDot';
import { RecentTasksDropdown } from './RecentTasksDropdown';

export function Header() {
  return (
    <header className="sticky top-0 z-40 bg-white border-b border-zinc-200">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
        <Link
          href="/"
          className="text-base font-semibold text-zinc-900 hover:text-indigo-600 transition-colors tracking-tight"
        >
          Content Engine
        </Link>

        <div className="flex items-center gap-4">
          <RecentTasksDropdown />
          <HealthDot />
        </div>
      </div>
    </header>
  );
}
