export function StyleAnchorBadge() {
  return (
    <div
      className="absolute top-2 right-2 text-[11px] font-medium px-2 py-0.5 rounded-full flex items-center gap-1"
      style={{
        background: 'rgba(15,17,23,0.85)',
        backdropFilter: 'blur(4px)',
        border: '1px solid var(--border2)',
        color: 'var(--fg2)',
      }}
    >
      <span>🎨</span>
      <span>Style Anchor</span>
    </div>
  );
}
