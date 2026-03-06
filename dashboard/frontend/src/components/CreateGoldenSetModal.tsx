import { useState, useEffect } from 'react';
import { X, Target } from 'lucide-react';
import { api } from '../services/api';
import type { CassetteListItem } from '../services/api';

interface CreateGoldenSetModalProps {
  projectId: string;
  onClose: () => void;
  onCreated: () => void;
  onError: (msg: string) => void;
}

export default function CreateGoldenSetModal({ projectId, onClose, onCreated, onError }: CreateGoldenSetModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [cassetteIds, setCassetteIds] = useState<string[]>([]);
  const [cassettes, setCassettes] = useState<CassetteListItem[]>([]);
  const [useThresholds, setUseThresholds] = useState(false);
  const [costThreshold, setCostThreshold] = useState('1.0');
  const [latencyThreshold, setLatencyThreshold] = useState('30000');
  const [tokenThreshold, setTokenThreshold] = useState('100000');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (projectId) {
      api.listCassettes(projectId).then(setCassettes).catch(() => {});
    }
  }, [projectId]);

  const toggleCassette = (id: string) => {
    setCassetteIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const handleSubmit = async () => {
    if (!name.trim()) { setError('Name is required'); return; }
    setError('');
    setLoading(true);
    try {
      const body: { name: string; description?: string; cassette_ids?: string[]; thresholds?: Record<string, unknown> } = { name: name.trim() };
      if (description.trim()) body.description = description.trim();
      if (cassetteIds.length > 0) body.cassette_ids = cassetteIds;
      if (useThresholds) {
        body.thresholds = {
          max_cost_usd: parseFloat(costThreshold) || 1.0,
          max_latency_ms: parseInt(latencyThreshold) || 30000,
          max_tokens: parseInt(tokenThreshold) || 100000,
        };
      }
      await api.createGoldenSet(projectId, body);
      onCreated();
      onClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to create golden set';
      setError(msg);
      onError(msg);
    } finally {
      setLoading(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    background: 'var(--bg)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text)',
    fontSize: 13,
    outline: 'none',
    fontFamily: 'var(--font-sans)',
    boxSizing: 'border-box',
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 14, width: 520, maxHeight: '90vh', overflow: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '18px 22px', borderBottom: '1px solid var(--border-subtle)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Target size={15} color="var(--accent)" />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>New Golden Set</span>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', display: 'flex', padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Name */}
          <div>
            <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', marginBottom: 6, display: 'block' }}>Name *</label>
            <input value={name} onChange={e => { setName(e.target.value); setError(''); }} placeholder="e.g. baseline-v1" style={inputStyle} />
          </div>

          {/* Description */}
          <div>
            <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', marginBottom: 6, display: 'block' }}>Description</label>
            <textarea value={description} onChange={e => setDescription(e.target.value)} placeholder="What this golden set validates…" rows={3} style={{ ...inputStyle, resize: 'vertical' }} />
          </div>

          {/* Cassette selector */}
          {cassettes.length > 0 && (
            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', marginBottom: 6, display: 'block' }}>
                Seed Cassettes ({cassetteIds.length} selected)
              </label>
              <div style={{
                maxHeight: 140, overflowY: 'auto', border: '1px solid var(--border)',
                borderRadius: 8, background: 'var(--bg)',
              }}>
                {cassettes.map(c => (
                  <label
                    key={c.id}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '7px 12px', cursor: 'pointer', fontSize: 12,
                      color: cassetteIds.includes(c.id) ? 'var(--text)' : 'var(--text-2)',
                      borderBottom: '1px solid var(--border-subtle)',
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-raised)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <input
                      type="checkbox"
                      checked={cassetteIds.includes(c.id)}
                      onChange={() => toggleCassette(c.id)}
                      style={{ accentColor: 'var(--accent)' }}
                    />
                    <span style={{ fontFamily: 'var(--font-mono)', flex: 1 }}>{c.name}</span>
                    <span style={{ color: 'var(--text-3)', fontSize: 11 }}>{c.agent_name}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Thresholds */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 12, color: 'var(--text-2)' }}>
              <input type="checkbox" checked={useThresholds} onChange={e => setUseThresholds(e.target.checked)} style={{ accentColor: 'var(--accent)' }} />
              Set custom thresholds
            </label>
            {useThresholds && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginTop: 10 }}>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4, display: 'block' }}>Max Cost ($)</label>
                  <input value={costThreshold} onChange={e => setCostThreshold(e.target.value)} style={inputStyle} />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4, display: 'block' }}>Max Latency (ms)</label>
                  <input value={latencyThreshold} onChange={e => setLatencyThreshold(e.target.value)} style={inputStyle} />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4, display: 'block' }}>Max Tokens</label>
                  <input value={tokenThreshold} onChange={e => setTokenThreshold(e.target.value)} style={inputStyle} />
                </div>
              </div>
            )}
          </div>

          {error && (
            <div style={{ fontSize: 12, color: 'var(--red)', padding: '8px 12px', background: 'rgba(248,113,113,0.08)', borderRadius: 8, border: '1px solid rgba(248,113,113,0.2)' }}>
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '14px 22px', borderTop: '1px solid var(--border-subtle)',
          display: 'flex', justifyContent: 'flex-end', gap: 10,
        }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', background: 'var(--bg)', border: '1px solid var(--border)',
            borderRadius: 8, color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'var(--font-sans)',
          }}>Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{
              padding: '8px 20px',
              background: loading ? 'var(--bg-raised)' : 'linear-gradient(135deg, #a78bfa, #8b5cf6)',
              border: 'none', borderRadius: 8,
              color: 'white', fontSize: 13, fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-sans)', opacity: loading ? 0.6 : 1,
            }}
          >{loading ? 'Creating…' : 'Create Golden Set'}</button>
        </div>
      </div>
    </div>
  );
}
