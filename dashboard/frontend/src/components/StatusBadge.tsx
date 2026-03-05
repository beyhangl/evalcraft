interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

const config: Record<string, { label: string; color: string; dot: string }> = {
  pass:     { label: 'Pass',     color: 'rgba(52,211,153,0.12)', dot: '#34d399' },
  fail:     { label: 'Fail',     color: 'rgba(248,113,113,0.12)', dot: '#f87171' },
  running:  { label: 'Running',  color: 'rgba(251,191,36,0.12)',  dot: '#fbbf24' },
  pending:  { label: 'Pending',  color: 'rgba(113,113,122,0.12)', dot: '#71717a' },
  critical: { label: 'Critical', color: 'rgba(248,113,113,0.12)', dot: '#f87171' },
  high:     { label: 'High',     color: 'rgba(251,146,60,0.12)',  dot: '#fb923c' },
  medium:   { label: 'Medium',   color: 'rgba(251,191,36,0.12)',  dot: '#fbbf24' },
  low:      { label: 'Low',      color: 'rgba(96,165,250,0.12)',  dot: '#60a5fa' },
  owner:    { label: 'Owner',    color: 'rgba(167,139,250,0.12)', dot: '#a78bfa' },
  admin:    { label: 'Admin',    color: 'rgba(96,165,250,0.12)',  dot: '#60a5fa' },
  member:   { label: 'Member',   color: 'rgba(113,113,122,0.12)', dot: '#71717a' },
};

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const c = config[status] ?? { label: status, color: 'rgba(113,113,122,0.12)', dot: '#71717a' };
  const isRunning = status === 'running';
  const pad = size === 'sm' ? '2px 8px' : '3px 10px';
  const fs = size === 'sm' ? '11px' : '12px';

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '5px',
      padding: pad,
      background: c.color,
      borderRadius: '100px',
      fontSize: fs,
      fontWeight: 500,
      color: c.dot,
      fontFamily: 'var(--font-mono)',
      letterSpacing: '0.01em',
      whiteSpace: 'nowrap',
    }}>
      <span style={{
        width: 6,
        height: 6,
        borderRadius: '50%',
        background: c.dot,
        flexShrink: 0,
        animation: isRunning ? 'pulse 1.5s ease-in-out infinite' : 'none',
      }} />
      {c.label}
      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }`}</style>
    </span>
  );
}
