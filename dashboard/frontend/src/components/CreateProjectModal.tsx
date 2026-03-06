import { useState } from 'react';
import { X, FolderPlus } from 'lucide-react';
import { api } from '../services/api';

interface CreateProjectModalProps {
  onClose: () => void;
  onCreated: () => void;
  onError: (msg: string) => void;
}

export default function CreateProjectModal({ onClose, onCreated, onError }: CreateProjectModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!name.trim()) { setError('Project name is required'); return; }
    setError('');
    setLoading(true);
    try {
      const body: { name: string; description?: string } = { name: name.trim() };
      if (description.trim()) body.description = description.trim();
      await api.createProject(body);
      onCreated();
      onClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to create project';
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
          borderRadius: 14, width: 440, maxHeight: '90vh', overflow: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '18px 22px', borderBottom: '1px solid var(--border-subtle)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FolderPlus size={15} color="var(--accent)" />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>New Project</span>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', display: 'flex', padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', marginBottom: 6, display: 'block' }}>Project Name *</label>
            <input
              value={name}
              onChange={e => { setName(e.target.value); setError(''); }}
              placeholder="e.g. my-agent"
              style={inputStyle}
              autoFocus
            />
          </div>

          <div>
            <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', marginBottom: 6, display: 'block' }}>Description</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="What this project evaluates…"
              rows={3}
              style={{ ...inputStyle, resize: 'vertical' }}
            />
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
          >{loading ? 'Creating…' : 'Create Project'}</button>
        </div>
      </div>
    </div>
  );
}
