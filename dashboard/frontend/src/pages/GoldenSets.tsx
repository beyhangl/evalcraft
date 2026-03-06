import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Target, Calendar } from 'lucide-react';
import Layout from '../components/Layout';
import { SkeletonCard } from '../components/Skeleton';
import CreateGoldenSetModal from '../components/CreateGoldenSetModal';
import { useAuth } from '../context/AuthContext';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { ToastMessage } from '../components/Toast';
import type { GoldenSetResponse, PaginatedResponse } from '../services/api';

interface GoldenSetsProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

export default function GoldenSets({ onLogout, addToast }: GoldenSetsProps) {
  const navigate = useNavigate();
  const { currentProject } = useAuth();
  const projectId = currentProject?.id ?? '';
  const [showCreate, setShowCreate] = useState(false);

  const { data: paginated, loading, refetch } = useApi<PaginatedResponse<GoldenSetResponse>>(
    () => projectId ? api.listGoldenSets(projectId) : Promise.resolve({ items: [], total: 0, page: 1, page_size: 50 }),
    [projectId],
  );
  const goldenSets = paginated?.items ?? [];

  const actions = (
    <button
      onClick={() => setShowCreate(true)}
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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
          <SkeletonCard height={160} />
          <SkeletonCard height={160} />
          <SkeletonCard height={160} />
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Golden Sets" actions={actions} onLogout={onLogout}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
        {goldenSets.map(gs => (
          <div
            key={gs.id}
            onClick={() => navigate(`/golden-sets/${gs.id}`)}
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', padding: 22,
              transition: 'border-color 0.2s, transform 0.15s',
              cursor: 'pointer',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
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
              <span style={{ fontSize: 11, color: 'var(--accent)', fontWeight: 500 }}>
                View →
              </span>
            </div>
          </div>
        ))}
        {goldenSets.length === 0 && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            padding: '60px 20px', textAlign: 'center', gridColumn: '1 / -1',
          }}>
            <div style={{
              width: 48, height: 48, borderRadius: 12,
              background: 'var(--accent-glow)', border: '1px solid var(--accent)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: 16,
            }}>
              <Target size={20} color="var(--accent)" />
            </div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>No golden sets yet</div>
            <p style={{ fontSize: 13, color: 'var(--text-3)', margin: '0 0 20px', maxWidth: 340, lineHeight: 1.5 }}>
              Create a golden set to define quality baselines for your agent.
            </p>
            <button
              onClick={() => setShowCreate(true)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '8px 18px',
                background: 'linear-gradient(135deg, #a78bfa, #8b5cf6)',
                border: 'none', borderRadius: 8,
                color: 'white', fontSize: 13, fontWeight: 600,
                cursor: 'pointer', fontFamily: 'var(--font-sans)',
              }}
            >
              <Target size={13} /> Create Golden Set
            </button>
          </div>
        )}
      </div>

      {showCreate && projectId && (
        <CreateGoldenSetModal
          projectId={projectId}
          onClose={() => setShowCreate(false)}
          onCreated={() => { refetch(); addToast({ type: 'success', text: 'Golden set created!' }); }}
          onError={msg => addToast({ type: 'error', text: msg })}
        />
      )}
    </Layout>
  );
}
