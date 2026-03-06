import { Target, Calendar } from 'lucide-react';
import Layout from '../components/Layout';
import { useAuth } from '../context/AuthContext';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { ToastMessage } from '../components/Toast';
import type { GoldenSetResponse } from '../services/api';

interface GoldenSetsProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

export default function GoldenSets({ onLogout, addToast }: GoldenSetsProps) {
  const { currentProject } = useAuth();
  const projectId = currentProject?.id ?? '';

  const { data: goldenSets, loading } = useApi<GoldenSetResponse[]>(
    () => projectId ? api.listGoldenSets(projectId) : Promise.resolve([]),
    [projectId],
  );

  const actions = (
    <button
      onClick={() => addToast({ type: 'success', text: 'New golden set created' })}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '6px 14px',
        background: 'linear-gradient(135deg, #a78bfa, #8b5cf6)',
        border: 'none', borderRadius: 8,
        color: 'white', fontSize: 13, fontWeight: 600,
        cursor: 'pointer', fontFamily: 'var(--font-sans)',
      }}
    >
      <Target size={13} /> New Golden Set
    </button>
  );

  if (loading) {
    return (
      <Layout title="Golden Sets" actions={actions} onLogout={onLogout}>
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-3)', fontSize: 14 }}>Loading…</div>
      </Layout>
    );
  }

  return (
    <Layout title="Golden Sets" actions={actions} onLogout={onLogout}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
        {(goldenSets ?? []).map(gs => (
          <div
            key={gs.id}
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', padding: 22,
              transition: 'border-color 0.2s, transform 0.15s',
              cursor: 'default',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--border-subtle)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: 'var(--accent-glow)', border: '1px solid var(--accent)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Target size={14} color="var(--accent)" />
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>{gs.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>v{gs.version}</div>
                </div>
              </div>
            </div>

            <p style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 14, lineHeight: 1.5 }}>{gs.description}</p>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-3)' }}>
                <Calendar size={11} />
                {new Date(gs.updated_at).toLocaleDateString()}
              </div>
              <button
                onClick={() => addToast({ type: 'info', text: `Comparing ${gs.name}…` })}
                style={{
                  padding: '5px 12px', background: 'var(--bg-raised)',
                  border: '1px solid var(--border)', borderRadius: 7,
                  color: 'var(--text-2)', fontSize: 12, cursor: 'pointer',
                  fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent)'; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-2)'; }}
              >
                Compare
              </button>
            </div>
          </div>
        ))}
        {(goldenSets ?? []).length === 0 && (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-3)', fontSize: 14, gridColumn: '1 / -1' }}>
            No golden sets yet
          </div>
        )}
      </div>
    </Layout>
  );
}
