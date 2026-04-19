interface TopbarProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export function Topbar({ title, subtitle, actions }: TopbarProps) {
  return (
    <div
      className="h-[52px] flex items-center px-7 gap-3.5 flex-shrink-0"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      <span className="text-[14px] font-semibold" style={{ color: 'var(--fg1)' }}>
        {title}
      </span>
      {subtitle && (
        <span className="text-[12.5px] flex-1" style={{ color: 'var(--fg3)' }}>
          {subtitle}
        </span>
      )}
      {actions && (
        <div className="flex items-center gap-2.5 ml-auto">{actions}</div>
      )}
    </div>
  );
}
