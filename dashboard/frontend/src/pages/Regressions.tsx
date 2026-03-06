import { useState } from 'react';
import { AlertTriangle, Clock } from 'lucide-react';
import Layout from '../components/Layout';
import { useAuth } from '../context/AuthContext';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { ToastMessage } from '../components/Toast';
import type { RegressionEventResponse } from '../services/api';

interface RegressionsProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

const severityColors: Record<string, string> = {
  CRITICAL: '#f87171',
  WARNING: '#fbbf24',
  INFO: '#60a5fa',
};

export default function Regressions({ onLogout, addToast: _addToast }: RegressionsProps) {
  const { currentProject } = useAuth();
  const projectId = currentProject?.id ?? '';
  const [filter, setFilter] = useState<string>('all');

  const { data: regressions, loading } = useApi<RegressionEventResponse[]>(
    () => projectId ? api.listRegressions(projectId, filter !== 'all' ? filter : undefined) : Promise.resolve([]),
    [projectId, filter],
  );

  if (loading) {
    return (
      <Layout title="Regressions" onLogout={onLogout}>
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-3)', fontSize: 14 }}>Loading…</div>
      </Layout>
    );
  }

  const items = regressions ?? [];

  return (
    <Layout title="Regressions" onLogout={onLogout}>
      {/* Filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {['all', 'CRITICAL', 'WARNING', 'INFO'].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            style={{
              padding: '6px 14px',
              background: filter === s ? (s === 'all' ? 'var(--accent-glow)' : undefined) : 'var(--bg-card)',
              border: `1px solid ${filter === s ? (s === 'all' ? 'var(--accent)' : 'currentColor') : 'var(--border)'}`,
              borderRadius: 8,
              color: filter === s
                ? s === 'all' ? 'var(--accent)' : (severityColors[s] ?? 'var(--text-2)')
                : 'var(--text-2)',
              fontSize: 12, fontWeight: 500, cursor: 'pointer',
              fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
            }}
          >
            {s === 'all' ? `All (${items.length})` : s}
          </button>
        ))}
      </div>

      {/* Feed */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {items.map(reg => {
          const color = severityColors[reg.severity] ?? '#71717a';
          return (
            <div
              key={reg.id}
              style={{
                background: 'var(--bg-card)',
                border: `1px solid var(--border)`,
                borderLeft: `3px solid ${color}`,
                borderRadius: 10,
                padding: '16px 20px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flex: 1, minWidth: 0 }}>
                  <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 1, color }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                      <span style={{
                        fontSize: 10, padding: '2px 8px', borderRadius: 100,
                        background: `${color}18`, color, fontWeight: 600,
                        textTransform: 'uppercase',
                      }}>
                        {reg.severity}
                      </span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text)', fontWeight: 600 }}>
                        {reg.category}
                      </span>
                    </div>
                    <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5, marginBottom: 6 }}>
                      {reg.message}
                    </p>
                    {reg.details && (
                      <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                        {reg.details.golden_value !== undefined && <span>golden: {String(reg.details.golden_value)}</span>}
                        {reg.details.current_value !== undefined && <span> → current: {String(reg.details.current_value)}</span>}
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-3)', flexShrink: 0 }}>
                  <Clock size={11} />
                  {new Date(reg.created_at).toLocaleDateString()}
                </div>
              </div>
            </div>
          );
        })}
        {items.length === 0 && (
          <div style={{ textAlign: 'center', padding: '48px 20px', color: 'var(--text-3)', fontSize: 14 }}>
            No regressions found
          </div>
        )}
      </div>
    </Layout>
  );
}
