interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  style?: React.CSSProperties;
}

export function SkeletonLine({ width = '100%', height = 14, borderRadius = 6, style }: SkeletonProps) {
  return (
    <div style={{
      width, height, borderRadius,
      background: 'linear-gradient(90deg, var(--bg-raised) 25%, var(--border-subtle) 50%, var(--bg-raised) 75%)',
      backgroundSize: '200% 100%',
      animation: 'skeleton-pulse 1.5s ease-in-out infinite',
      ...style,
    }} />
  );
}

export function SkeletonCard({ height = 120, style }: SkeletonProps) {
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: 20, height,
      ...style,
    }}>
      <SkeletonLine width="60%" height={16} style={{ marginBottom: 12 }} />
      <SkeletonLine width="80%" height={12} style={{ marginBottom: 8 }} />
      <SkeletonLine width="40%" height={12} />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
        <SkeletonLine width="30%" height={14} />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{ padding: '14px 20px', borderBottom: i < rows - 1 ? '1px solid var(--border-subtle)' : 'none', display: 'flex', gap: 16 }}>
          <SkeletonLine width="25%" height={12} />
          <SkeletonLine width="15%" height={12} />
          <SkeletonLine width="20%" height={12} />
          <SkeletonLine width="10%" height={12} />
        </div>
      ))}
    </div>
  );
}

// Inject keyframes animation
const styleId = 'skeleton-styles';
if (typeof document !== 'undefined' && !document.getElementById(styleId)) {
  const style = document.createElement('style');
  style.id = styleId;
  style.textContent = `
    @keyframes skeleton-pulse {
      0% { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }
  `;
  document.head.appendChild(style);
}
