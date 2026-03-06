import { useState } from 'react';
import { Key, Trash2, Plus, Copy, Check } from 'lucide-react';
import Layout from '../components/Layout';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { ToastMessage } from '../components/Toast';
import type { APIKeyResponse } from '../services/api';

interface SettingsProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

export default function Settings({ onLogout, addToast }: SettingsProps) {
  const { data: keys, refetch } = useApi<APIKeyResponse[]>(() => api.listApiKeys(), []);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyKey = (id: string, prefix: string) => {
    navigator.clipboard.writeText(prefix).catch(() => {});
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const deleteKey = async (id: string) => {
    try {
      await api.revokeApiKey(id);
      addToast({ type: 'success', text: 'API key revoked' });
      refetch();
    } catch {
      addToast({ type: 'error', text: 'Failed to revoke key' });
    }
  };

  const createKey = async () => {
    try {
      const result = await api.createApiKey('default');
      addToast({ type: 'success', text: `API key created: ${result.full_key}` });
      refetch();
    } catch {
      addToast({ type: 'error', text: 'Failed to create key' });
    }
  };

  return (
    <Layout title="Settings" onLogout={onLogout}>
      {/* API Keys */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 24,
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
            onClick={createKey}
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
          {(keys ?? []).map(k => (
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
                  <code style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>{k.key_prefix}…</code>
                  <button
                    onClick={() => copyKey(k.id, k.key_prefix)}
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
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  {k.last_used_at ? `Last used ${new Date(k.last_used_at).toLocaleDateString()}` : 'Never used'}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                  Created {new Date(k.created_at).toLocaleDateString()}
                </div>
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
          {(keys ?? []).length === 0 && (
            <div style={{ textAlign: 'center', padding: '32px 20px', color: 'var(--text-3)', fontSize: 13 }}>
              No API keys yet
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
