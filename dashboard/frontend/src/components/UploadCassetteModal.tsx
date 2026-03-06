import { useState, useRef } from 'react';
import { X, Upload, FileJson, ClipboardPaste } from 'lucide-react';

interface UploadCassetteModalProps {
  projectId: string;
  onClose: () => void;
  onUploaded: () => void;
  onError: (msg: string) => void;
}

export default function UploadCassetteModal({ projectId, onClose, onUploaded, onError }: UploadCassetteModalProps) {
  const [mode, setMode] = useState<'paste' | 'file'>('paste');
  const [jsonText, setJsonText] = useState('');
  const [fileName, setFileName] = useState('');
  const [gitSha, setGitSha] = useState('');
  const [branch, setBranch] = useState('');
  const [ciRunUrl, setCiRunUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const fileDataRef = useRef<Record<string, unknown> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setError('');
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        fileDataRef.current = JSON.parse(ev.target?.result as string);
      } catch {
        setError('Invalid JSON file');
        fileDataRef.current = null;
      }
    };
    reader.readAsText(file);
  };

  const handleSubmit = async () => {
    setError('');
    let data: Record<string, unknown>;

    if (mode === 'paste') {
      if (!jsonText.trim()) { setError('Paste JSON content'); return; }
      try {
        data = JSON.parse(jsonText);
      } catch {
        setError('Invalid JSON'); return;
      }
    } else {
      if (!fileDataRef.current) { setError('Select a valid JSON file'); return; }
      data = fileDataRef.current;
    }

    setLoading(true);
    try {
      const { api } = await import('../services/api');
      const meta: { git_sha?: string; branch?: string; ci_run_url?: string } = {};
      if (gitSha) meta.git_sha = gitSha;
      if (branch) meta.branch = branch;
      if (ciRunUrl) meta.ci_run_url = ciRunUrl;
      await api.uploadCassette(projectId, data, meta);
      onUploaded();
      onClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Upload failed';
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
            <Upload size={15} color="var(--accent)" />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Upload Cassette</span>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', display: 'flex', padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Mode tabs */}
          <div style={{ display: 'flex', gap: 8 }}>
            {([
              { key: 'paste' as const, label: 'Paste JSON', icon: ClipboardPaste },
              { key: 'file' as const, label: 'Upload File', icon: FileJson },
            ]).map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setMode(key)}
                style={{
                  flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  padding: '8px 12px', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer',
                  fontFamily: 'var(--font-sans)',
                  background: mode === key ? 'var(--accent-glow)' : 'var(--bg)',
                  border: `1px solid ${mode === key ? 'var(--accent)' : 'var(--border)'}`,
                  color: mode === key ? 'var(--accent)' : 'var(--text-2)',
                  transition: 'all 0.15s',
                }}
              >
                <Icon size={13} /> {label}
              </button>
            ))}
          </div>

          {/* JSON input */}
          {mode === 'paste' ? (
            <textarea
              value={jsonText}
              onChange={e => { setJsonText(e.target.value); setError(''); }}
              placeholder='{"name": "my-cassette", ...}'
              rows={8}
              style={{
                ...inputStyle,
                fontFamily: 'var(--font-mono)',
                resize: 'vertical',
              }}
            />
          ) : (
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                style={{
                  width: '100%', padding: '20px', borderRadius: 8,
                  border: '2px dashed var(--border)',
                  background: 'var(--bg)', cursor: 'pointer',
                  color: 'var(--text-2)', fontSize: 13,
                  fontFamily: 'var(--font-sans)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  transition: 'border-color 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
              >
                <FileJson size={16} />
                {fileName || 'Choose a .json file'}
              </button>
            </div>
          )}

          {/* Optional metadata */}
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-3)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Optional Metadata
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <input placeholder="Git SHA" value={gitSha} onChange={e => setGitSha(e.target.value)} style={inputStyle} />
            <input placeholder="Branch" value={branch} onChange={e => setBranch(e.target.value)} style={inputStyle} />
          </div>
          <input placeholder="CI Run URL" value={ciRunUrl} onChange={e => setCiRunUrl(e.target.value)} style={inputStyle} />

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
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px', background: 'var(--bg)', border: '1px solid var(--border)',
              borderRadius: 8, color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'var(--font-sans)',
            }}
          >
            Cancel
          </button>
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
          >
            {loading ? 'Uploading…' : 'Upload'}
          </button>
        </div>
      </div>
    </div>
  );
}
