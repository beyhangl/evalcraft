import { useState } from 'react';
import { AlertTriangle, Clock, CheckCircle, Eye, EyeOff } from 'lucide-react';
import Layout from '../components/Layout';
import { SkeletonCard } from '../components/Skeleton';
import { useAuth } from '../context/AuthContext';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { ToastMessage } from '../components/Toast';
import type { RegressionEventResponse, PaginatedResponse } from '../services/api';

interface RegressionsProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

const severityColors: Record<string, string> = {
  CRITICAL: '#f87171',
  WARNING: '#fbbf24',
  INFO: '#60a5fa',
};

export default function Regressions({ onLogout, addToast }: RegressionsProps) {
  const { currentProject } = useAuth();
  const projectId = currentProject?.id ?? '';
  const [filter, setFilter] = useState<string>('all');
  const [showResolved, setShowResolved] = useState(false);
  const [resolving, setResolving] = useState<string | null>(null);

  const { data: paginated, loading, refetch } = useApi<PaginatedResponse<RegressionEventResponse>>(
    () => projectId ? api.listRegressions(projectId, filter !== 'all' ? filter : undefined) : Promise.resolve({ items: [], total: 0, page: 1, page_size: 50 }),
    [projectId, filter],
  );
  const regressions = paginated?.items ?? [];

  const handleResolve = async (id: string) => {
    setResolving(id);
    try {
      await api.resolveRegression(id);
      addToast({ type: 'success', text: 'Regression resolved' });
      refetch();
    } catch (err) {
      addToast({ type: 'error', text: err instanceof Error ? err.message : 'Failed to resolve' });
    } finally {
      setResolving(null);
    }
  };

  if (loading) {
    return (
      <Layout title="Regressions" onLogout={onLogout}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <SkeletonCard height={90} />
          <SkeletonCard height={90} />
          <SkeletonCard height={90} />
        </div>
      </Layout>
    );
  }

  const items = showResolved ? regressions : regressions.filter(r => !r.resolved);

  return (
    <Layout title="Regressions" onLogout={onLogout}>
      {/* Filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
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
        <div style={{ marginLeft: 'auto' }}>
          <button
            onClick={() => setShowResolved(v => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '6px 14px', background: 'var(--bg-card)',
              border: '1px solid var(--border)', borderRadius: 8,
              color: 'var(--text-3)', fontSize: 12, fontWeight: 500,
              cursor: 'pointer', fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
            }}
          >
            {showResolved ? <EyeOff size={12} /> : <Eye size={12} />}
            {showResolved ? 'Hide resolved' : 'Show resolved'}
          </button>
        </div>
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
                borderLeft: `3px solid ${reg.resolved ? 'var(--green)' : color}`,
                borderRadius: 10,
                padding: '16px 20px',
                opacity: reg.resolved ? 0.6 : 1,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flex: 1, minWidth: 0 }}>
                  {reg.resolved
                    ? <CheckCircle size={15} style={{ flexShrink: 0, marginTop: 1, color: 'var(--green)' }} />
                    : <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 1, color }} />
                  }
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
                      {reg.resolved && (
                        <span style={{
                          fontSize: 10, padding: '2px 8px', borderRadius: 100,
                          background: 'rgba(74, 222, 128, 0.15)', color: 'var(--green)',
                          fontWeight: 600, textTransform: 'uppercase',
                        }}>
                          Resolved
                        </span>
                      )}
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
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-3)' }}>
                    <Clock size={11} />
                    {new Date(reg.created_at).toLocaleDateString()}
                  </div>
                  {!reg.resolved && (
                    <button
                      onClick={() => handleResolve(reg.id)}
                      disabled={resolving === reg.id}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 4,
                        padding: '4px 10px', background: 'var(--bg-raised)',
                        border: '1px solid var(--border)', borderRadius: 6,
                        color: 'var(--green)', fontSize: 11, fontWeight: 500,
                        cursor: resolving === reg.id ? 'wait' : 'pointer',
                        fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
                        opacity: resolving === reg.id ? 0.5 : 1,
                      }}
                    >
                      <CheckCircle size={11} />
                      {resolving === reg.id ? 'Resolving…' : 'Resolve'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        {items.length === 0 && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            padding: '60px 20px', textAlign: 'center',
          }}>
            <div style={{
              width: 48, height: 48, borderRadius: 12,
              background: 'rgba(74, 222, 128, 0.1)', border: '1px solid var(--green)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: 16,
            }}>
              <CheckCircle size={20} color="var(--green)" />
            </div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>
              No regressions {showResolved ? '' : 'open'}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-3)' }}>
              {regressions.length > 0 ? 'All regressions have been resolved.' : 'No regression events detected yet.'}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
