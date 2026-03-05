import type { ReactNode } from 'react';

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  subColor?: string;
  icon?: ReactNode;
  accentColor?: string;
}

export default function MetricCard({ label, value, sub, subColor, icon, accentColor = 'var(--accent)' }: MetricCardProps) {
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding: '20px 24px',
      position: 'relative',
      overflow: 'hidden',
      transition: 'border-color 0.2s',
    }}
    onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--border-subtle)')}
    onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
    >
      {/* subtle gradient top-right */}
      <div style={{
        position: 'absolute',
        top: 0,
        right: 0,
        width: 80,
        height: 80,
        background: `radial-gradient(circle at top right, ${accentColor}18, transparent 70%)`,
        pointerEvents: 'none',
      }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{ fontSize: 13, color: 'var(--text-2)', fontWeight: 500, letterSpacing: '0.01em' }}>
          {label}
        </span>
        {icon && (
          <span style={{ color: accentColor, opacity: 0.7 }}>{icon}</span>
        )}
      </div>

      <div style={{ marginTop: 12 }}>
        <span style={{ fontSize: 28, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em', lineHeight: 1 }}>
          {value}
        </span>
        {sub && (
          <span style={{
            display: 'block',
            marginTop: 6,
            fontSize: 12,
            color: subColor ?? 'var(--text-3)',
            fontWeight: 500,
          }}>
            {sub}
          </span>
        )}
      </div>
    </div>
  );
}
