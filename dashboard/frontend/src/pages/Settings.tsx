import { useState } from 'react';
import { Key, Trash2, Plus, Copy, Check, Users, Shield } from 'lucide-react';
import Layout from '../components/Layout';
import StatusBadge from '../components/StatusBadge';
import { mockApiKeys, mockTeam } from '../data/mock';
import type { ToastMessage } from '../components/Toast';

interface SettingsProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

export default function Settings({ onLogout, addToast }: SettingsProps) {
  const [keys, setKeys] = useState(mockApiKeys);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyKey = (id: string, key: string) => {
    navigator.clipboard.writeText(key).catch(() => {});
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const deleteKey = (id: string) => {
    setKeys(prev => prev.filter(k => k.id !== id));
    addToast({ type: 'success', text: 'API key revoked' });
  };

  return (
    <Layout title="Settings" onLogout={onLogout}>
      {/* API Keys */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 24, marginBottom: 20,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Key size={16} color="var(--accent)" />
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>API Keys</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>Manage keys for CI/CD and SDK access</div>
            </div>
          </div>
          <button
            onClick={() => addToast({ type: 'success', text: 'New API key created' })}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 14px',
              background: 'linear-gradient(135deg, #a78bfa, #8b5cf6)',
              border: 'none', borderRadius: 8,
              color: 'white', fontSize: 13, fontWeight: 600,
              cursor: 'pointer', fontFamily: 'var(--font-sans)',
            }}
          >
            <Plus size={13} /> New Key
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {keys.map(k => (
            <div
              key={k.id}
              style={{
                display: 'flex', alignItems: 'center', gap: 16,
                padding: '14px 16px',
                background: 'var(--bg-raised)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 10,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>{k.name}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <code style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>{k.key}</code>
                  <button
                    onClick={() => copyKey(k.id, k.key)}
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      color: copiedId === k.id ? 'var(--green)' : 'var(--text-3)',
                      padding: 2, display: 'flex',
                    }}
                  >
                    {copiedId === k.id ? <Check size={12} /> : <Copy size={12} />}
                  </button>
                </div>
              </div>
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Last used {k.lastUsed}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>Created {k.created}</div>
              </div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', maxWidth: 180 }}>
                {k.scopes.map(s => (
                  <span key={s} style={{
                    fontSize: 10, padding: '2px 6px',
                    background: 'var(--accent-glow)', borderRadius: 4,
                    color: 'var(--accent)', fontFamily: 'var(--font-mono)',
                  }}>
                    {s}
                  </span>
                ))}
              </div>
              <button
                onClick={() => deleteKey(k.id)}
                style={{
                  background: 'none', border: '1px solid var(--border)',
                  borderRadius: 6, padding: '5px 8px', cursor: 'pointer',
                  color: 'var(--text-3)', transition: 'all 0.15s', display: 'flex',
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(248,113,113,0.4)'; e.currentTarget.style.color = 'var(--red)'; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-3)'; }}
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Team Members */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 24,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Users size={16} color="var(--accent)" />
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Team Members</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{mockTeam.length} members</div>
            </div>
          </div>
          <button
            onClick={() => addToast({ type: 'info', text: 'Invite link copied to clipboard' })}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 14px', background: 'var(--bg-raised)',
              border: '1px solid var(--border)', borderRadius: 8,
              color: 'var(--text-2)', fontSize: 13, fontWeight: 500,
              cursor: 'pointer', fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--text)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-2)'; }}
          >
            <Plus size={13} /> Invite
          </button>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Member', 'Email', 'Role', 'Joined'].map(h => (
                  <th key={h} style={{
                    padding: '10px 16px', textAlign: 'left',
                    fontSize: 11, fontWeight: 600, color: 'var(--text-3)',
                    letterSpacing: '0.06em', textTransform: 'uppercase',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {mockTeam.map((m, i) => (
                <tr key={m.id} style={{ borderBottom: i < mockTeam.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{
                        width: 28, height: 28, borderRadius: '50%',
                        background: 'linear-gradient(135deg, #a78bfa40, #60a5fa40)',
                        border: '1px solid var(--border)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 10, fontWeight: 600, color: 'var(--accent)',
                      }}>
                        {m.avatar}
                      </div>
                      <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{m.name}</span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: 13, color: 'var(--text-2)' }}>{m.email}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {m.role === 'owner' && <Shield size={12} color="var(--accent)" />}
                      <StatusBadge status={m.role} size="sm" />
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--text-3)' }}>{m.joined}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  );
}
