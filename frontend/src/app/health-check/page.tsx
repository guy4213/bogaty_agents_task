'use client';

import { useHealth } from '@/hooks/useHealth';
import { Topbar } from '@/components/Topbar';

const SERVICE_ICONS: Record<string, React.ReactNode> = {
  claude: (
    <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M7 10l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  gemini: (
    <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5">
      <path d="M10 2L12.5 8.5H19L13.5 12.5L15.5 19L10 15L4.5 19L6.5 12.5L1 8.5H7.5L10 2Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
    </svg>
  ),
  s3: (
    <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5">
      <ellipse cx="10" cy="6" rx="7" ry="3" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M3 6v8c0 1.657 3.134 3 7 3s7-1.343 7-3V6" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M3 10c0 1.657 3.134 3 7 3s7-1.343 7-3" stroke="currentColor" strokeWidth="1.4"/>
    </svg>
  ),
};

function statusStyle(status: string): React.CSSProperties {
  if (status === 'healthy' || status === 'up')      return { background: 'rgba(34,197,94,0.1)',   color: '#4ade80',             border: '1px solid rgba(34,197,94,0.2)' };
  if (status === 'degraded' || status === 'down')   return { background: 'rgba(239,68,68,0.1)',   color: '#f87171',             border: '1px solid rgba(239,68,68,0.2)' };
  return                                                   { background: 'rgba(245,158,11,0.1)',   color: '#fbbf24',             border: '1px solid rgba(245,158,11,0.2)' };
}

function circuitStyle(state: string): React.CSSProperties {
  if (state === 'closed')    return { color: '#4ade80' };
  if (state === 'open')      return { color: '#f87171' };
  return                            { color: '#fbbf24' };
}

function overallBannerStyle(overall: string): React.CSSProperties {
  if (overall === 'healthy') return { background: 'rgba(34,197,94,0.08)',  border: '1px solid rgba(34,197,94,0.2)',  color: '#4ade80' };
  if (overall === 'down')    return { background: 'rgba(239,68,68,0.08)',  border: '1px solid rgba(239,68,68,0.2)',  color: '#f87171' };
  return                            { background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', color: '#fbbf24' };
}

export default function HealthPage() {
  const { data, isLoading, refetch, dataUpdatedAt } = useHealth();

  const lastChecked = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null;

  return (
    <>
      <Topbar
        title="Health"
        subtitle={lastChecked ? `Last checked ${lastChecked}` : 'Checking…'}
        actions={
          <button
            type="button"
            onClick={() => refetch()}
            className="flex items-center gap-1.5 text-[12px] font-medium px-3 py-[5px] rounded-[var(--radius-sm)] transition-colors"
            style={{ border: '1px solid var(--border2)', color: 'var(--fg2)' }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface2)'; (e.currentTarget as HTMLElement).style.color = 'var(--fg1)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--fg2)'; }}
          >
            <svg viewBox="0 0 14 14" fill="none" className="w-3 h-3">
              <path d="M12 7A5 5 0 112 7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
              <path d="M12 3v4h-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Refresh
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 flex flex-col gap-6 max-w-3xl">
        {isLoading && (
          <div className="flex items-center gap-2 py-16 text-sm" style={{ color: 'var(--fg3)' }}>
            <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--accent-dim)', borderTopColor: 'var(--accent)' }} />
            Checking services…
          </div>
        )}

        {data && (
          <>
            {/* Overall banner */}
            <div className="flex items-center gap-3 px-4 py-3 rounded-[var(--radius)]" style={overallBannerStyle(data.overall)}>
              <span className="text-lg">
                {data.overall === 'healthy' ? '✓' : data.overall === 'down' ? '✗' : '⚠'}
              </span>
              <div>
                <p className="text-[14px] font-semibold capitalize">{data.overall}</p>
                <p className="text-[11px] opacity-70">
                  {new Date(data.timestamp).toLocaleString()}
                </p>
              </div>
            </div>

            {/* Service cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {data.services.map((svc) => (
                <div
                  key={svc.service}
                  className="rounded-[var(--radius)] p-5 flex flex-col gap-4"
                  style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
                >
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span style={{ color: 'var(--fg2)' }}>{SERVICE_ICONS[svc.service] ?? SERVICE_ICONS['s3']}</span>
                      <span className="text-[14px] font-semibold capitalize" style={{ color: 'var(--fg1)' }}>
                        {svc.service}
                      </span>
                    </div>
                    <span
                      className="text-[10.5px] font-semibold px-2 py-0.5 rounded capitalize"
                      style={statusStyle(svc.status)}
                    >
                      {svc.status}
                    </span>
                  </div>

                  {/* Details */}
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-[11px]" style={{ color: 'var(--fg3)' }}>Circuit</span>
                      <span className="text-[11px] font-semibold font-mono capitalize" style={circuitStyle(svc.circuit_state)}>
                        {svc.circuit_state.replace('_', ' ')}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-[11px]" style={{ color: 'var(--fg3)' }}>Latency</span>
                      <span className="text-[11px] font-mono" style={{ color: svc.latency_ms !== null ? 'var(--fg1)' : 'var(--fg3)' }}>
                        {svc.latency_ms !== null ? `${svc.latency_ms}ms` : '—'}
                      </span>
                    </div>
                  </div>

                  {/* Error */}
                  {svc.error && (
                    <p
                      className="text-[11px] font-mono px-2.5 py-2 rounded-[var(--radius-sm)] break-words"
                      style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--danger)', border: '1px solid rgba(239,68,68,0.15)' }}
                    >
                      {svc.error}
                    </p>
                  )}
                </div>
              ))}
            </div>

            {/* Circuit breaker legend */}
            <div
              className="rounded-[var(--radius-sm)] px-4 py-3"
              style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
            >
              <p className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--fg3)' }}>Circuit Breaker States</p>
              <div className="flex flex-wrap gap-4 text-[12px]">
                <span><span style={{ color: '#4ade80' }}>closed</span> — normal, requests passing through</span>
                <span><span style={{ color: '#f87171' }}>open</span> — tripped, requests blocked (5 failures / 120s)</span>
                <span><span style={{ color: '#fbbf24' }}>half_open</span> — recovery probe every 60s</span>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
