import { useState } from 'react';
import { Target, GitBranch, Calendar, X } from 'lucide-react';
import Layout from '../components/Layout';
import { mockGoldenSets } from '../data/mock';
import type { ToastMessage } from '../components/Toast';

interface GoldenSetsProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

const historyVersions = [
  { v: 'v4', date: '2026-03-03', changes: '+3 cassettes, updated thresholds', author: 'Alex Rivera' },
  { v: 'v3', date: '2026-02-15', changes: 'Fixed flaky test in edge case #7', author: 'Sam Chen' },
  { v: 'v2', date: '2026-01-28', changes: 'Added payment failure scenarios', author: 'Alex Rivera' },
  { v: 'v1', date: '2025-12-20', changes: 'Initial golden set creation', author: 'Alex Rivera' },
];

export default function GoldenSets({ onLogout, addToast }: GoldenSetsProps) {
  const [historyOpen, setHistoryOpen] = useState<string | null>(null);

  const openHistory = (id: string) => setHistoryOpen(id);
  const closeHistory = () => setHistoryOpen(null);

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

  const historyGs = mockGoldenSets.find(g => g.id === historyOpen);

  return (
    <Layout title="Golden Sets" actions={actions} onLogout={onLogout}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
        {mockGoldenSets.map(gs => {
          const passColor = gs.passRate >= 90 ? 'var(--green)' : gs.passRate >= 75 ? 'var(--orange)' : 'var(--red)';
          return (
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
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: 8,
                    background: 'var(--accent-glow)', border: '1px solid var(--accent)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Target size={14} color="var(--accent)" />
                  </div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>{gs.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{gs.cassettes} cassettes · {gs.version}</div>
                  </div>
                </div>
                {/* Pass rate badge */}
                <div style={{
                  fontSize: 14, fontWeight: 700, color: passColor,
                  background: `${passColor}18`, border: `1px solid ${passColor}40`,
                  borderRadius: 8, padding: '4px 10px',
                  fontFamily: 'var(--font-mono)',
                }}>
                  {gs.passRate}%
                </div>
              </div>

              <p style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 14, lineHeight: 1.5 }}>{gs.description}</p>

              {/* Progress bar */}
              <div style={{ marginBottom: 14 }}>
                <div style={{ height: 4, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${gs.passRate}%`, background: passColor, borderRadius: 4 }} />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-3)' }}>
                  <Calendar size={11} />
                  {gs.updated}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
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
                  <button
                    onClick={() => openHistory(gs.id)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      padding: '5px 12px', background: 'var(--bg-raised)',
                      border: '1px solid var(--border)', borderRadius: 7,
                      color: 'var(--text-2)', fontSize: 12, cursor: 'pointer',
                      fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--border-subtle)'; e.currentTarget.style.color = 'var(--text)'; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-2)'; }}
                  >
                    <GitBranch size={11} /> History
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Version history modal */}
      {historyOpen && historyGs && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 1000, padding: 16,
          }}
          onClick={closeHistory}
        >
          <div
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 16, padding: 28, width: '100%', maxWidth: 480,
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text)' }}>Version History</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>{historyGs.name}</div>
              </div>
              <button onClick={closeHistory} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 4 }}>
                <X size={18} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {historyVersions.map((v, i) => (
                <div key={v.v} style={{ display: 'flex', gap: 12, position: 'relative' }}>
                  {/* Line */}
                  {i < historyVersions.length - 1 && (
                    <div style={{ position: 'absolute', left: 11, top: 24, bottom: 0, width: 1, background: 'var(--border)' }} />
                  )}
                  <div style={{
                    width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                    background: i === 0 ? 'var(--accent-glow)' : 'var(--border)',
                    border: `2px solid ${i === 0 ? 'var(--accent)' : 'var(--border-subtle)'}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    zIndex: 1,
                  }}>
                    {i === 0 && <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)' }} />}
                  </div>
                  <div style={{ paddingBottom: 20, flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: i === 0 ? 'var(--accent)' : 'var(--text)', fontFamily: 'var(--font-mono)' }}>{v.v}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{v.date}</span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>{v.changes}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>by {v.author}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}
