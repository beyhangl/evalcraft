import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Target, Calendar, Settings } from 'lucide-react';
import Layout from '../components/Layout';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import { SkeletonCard } from '../components/Skeleton';
import type { ToastMessage } from '../components/Toast';
import type { GoldenSetDetailResponse } from '../services/api';

interface GoldenSetDetailProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

export default function GoldenSetDetail({ onLogout }: GoldenSetDetailProps) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: goldenSet, loading } = useApi<GoldenSetDetailResponse>(
    () => id ? api.getGoldenSet(id) : Promise.reject('No ID'),
    [id],
  );

  const actions = (
    <button
      onClick={() => navigate('/golden-sets')}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '6px 14px', background: 'var(--bg-raised)',
        border: '1px solid var(--border)', borderRadius: 8,
        color: 'var(--text-2)', fontSize: 13, fontWeight: 500,
        cursor: 'pointer', fontFamily: 'var(--font-sans)',
      }}
    >
      <ArrowLeft size={13} /> Back
    </button>
  );

  if (loading) {
    return (
      <Layout title="Golden Set" actions={actions} onLogout={onLogout}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <SkeletonCard height={80} />
          <SkeletonCard height={200} />
        </div>
      </Layout>
    );
  }

  if (!goldenSet) {
    return (
      <Layout title="Golden Set" actions={actions} onLogout={onLogout}>
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-3)', fontSize: 14 }}>
          Golden set not found
        </div>
      </Layout>
    );
  }

  const thresholds = goldenSet.thresholds || {};

  return (
    <Layout title={goldenSet.name} actions={actions} onLogout={onLogout}>
      {/* Header */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 24, marginBottom: 20,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 10,
            background: 'var(--accent-glow)', border: '1px solid var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Target size={18} color="var(--accent)" />
          </div>
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text)', margin: 0 }}>{goldenSet.name}</h2>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>v{goldenSet.version}</div>
          </div>
        </div>
        {goldenSet.description && (
          <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5, margin: 0 }}>{goldenSet.description}</p>
        )}
        <div style={{ display: 'flex', gap: 16, marginTop: 12, fontSize: 12, color: 'var(--text-3)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Calendar size={12} /> Created {new Date(goldenSet.created_at).toLocaleDateString()}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Calendar size={12} /> Updated {new Date(goldenSet.updated_at).toLocaleDateString()}
          </div>
        </div>
      </div>

      {/* Thresholds */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden',
      }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Settings size={14} color="var(--text-3)" />
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Thresholds</span>
        </div>
        <div style={{ padding: 0 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <th style={{ padding: '10px 24px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Setting</th>
                <th style={{ padding: '10px 24px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Value</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(thresholds).map(([key, value], i, arr) => (
                <tr key={key} style={{ borderBottom: i < arr.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                  <td style={{ padding: '10px 24px', fontSize: 13, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>{key}</td>
                  <td style={{ padding: '10px 24px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{String(value ?? 'null')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  );
}
