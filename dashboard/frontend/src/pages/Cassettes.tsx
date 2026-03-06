import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Upload, ChevronUp, ChevronDown, Eye } from 'lucide-react';
import Layout from '../components/Layout';
import { SkeletonTable } from '../components/Skeleton';
import UploadCassetteModal from '../components/UploadCassetteModal';
import { useAuth } from '../context/AuthContext';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { ToastMessage } from '../components/Toast';
import type { CassetteListItem, PaginatedResponse } from '../services/api';

type SortKey = 'name' | 'created_at' | 'total_tokens' | 'total_cost_usd';
type SortDir = 'asc' | 'desc';

interface CassettesProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

export default function Cassettes({ onLogout, addToast }: CassettesProps) {
  const navigate = useNavigate();
  const { currentProject } = useAuth();
  const projectId = currentProject?.id ?? '';
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('created_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [showUpload, setShowUpload] = useState(false);

  const { data: paginated, loading, refetch } = useApi<PaginatedResponse<CassetteListItem>>(
    () => projectId ? api.listCassettes(projectId) : Promise.resolve({ items: [], total: 0, page: 1, page_size: 50 }),
    [projectId],
  );
  const cassettes = paginated?.items ?? [];

  const filtered = useMemo(() => {
    let list = cassettes.filter(c => {
      if (search && !c.name.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
    list = [...list].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [cassettes, search, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const SortIcon = ({ k }: { k: SortKey }) => sortKey === k
    ? (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)
    : <ChevronDown size={12} style={{ opacity: 0.3 }} />;

  const fmtDuration = (ms: number) => ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;

  const actions = (
    <button
      onClick={() => setShowUpload(true)}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '6px 14px',
        background: 'linear-gradient(135deg, #a78bfa, #8b5cf6)',
        border: 'none', borderRadius: 8,
        color: 'white', fontSize: 13, fontWeight: 600,
        cursor: 'pointer', fontFamily: 'var(--font-sans)',
      }}
    >
      <Upload size={13} /> Upload Cassette
    </button>
  );

  if (loading) {
    return (
      <Layout title="Cassettes" actions={actions} onLogout={onLogout}>
        <SkeletonTable rows={6} />
      </Layout>
    );
  }

  return (
    <Layout title="Cassettes" actions={actions} onLogout={onLogout}>
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 220, position: 'relative' }}>
          <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)' }} />
          <input
            placeholder="Search cassettes…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              width: '100%',
              padding: '8px 12px 8px 34px',
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 9,
              color: 'var(--text)',
              fontSize: 13,
              outline: 'none',
            }}
            onFocus={e => e.target.style.borderColor = 'var(--accent)'}
            onBlur={e => e.target.style.borderColor = 'var(--border)'}
          />
        </div>
      </div>

      {/* Table */}
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {([
                  { label: 'Name', key: 'name' as SortKey },
                  { label: 'Agent', key: null },
                  { label: 'Date', key: 'created_at' as SortKey },
                  { label: 'Duration', key: null },
                  { label: 'Tokens', key: 'total_tokens' as SortKey },
                  { label: 'Cost', key: 'total_cost_usd' as SortKey },
                  { label: 'Actions', key: null },
                ] as const).map(({ label, key }) => (
                  <th
                    key={label}
                    onClick={key ? () => toggleSort(key) : undefined}
                    style={{
                      padding: '11px 20px', textAlign: 'left',
                      fontSize: 11, fontWeight: 600, color: 'var(--text-3)',
                      letterSpacing: '0.06em', textTransform: 'uppercase',
                      cursor: key ? 'pointer' : 'default',
                      userSelect: 'none',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      {label}
                      {key && <SortIcon k={key} />}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((c, i) => (
                <tr
                  key={c.id}
                  style={{
                    borderBottom: i < filtered.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-raised)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '12px 20px', fontSize: 13, color: 'var(--text)', fontFamily: 'var(--font-mono)', fontWeight: 500 }}>
                    {c.name}
                  </td>
                  <td style={{ padding: '12px 20px', fontSize: 12, color: 'var(--text-2)' }}>{c.agent_name}</td>
                  <td style={{ padding: '12px 20px', fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{new Date(c.created_at).toLocaleDateString()}</td>
                  <td style={{ padding: '12px 20px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{fmtDuration(c.total_duration_ms)}</td>
                  <td style={{ padding: '12px 20px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{c.total_tokens.toLocaleString()}</td>
                  <td style={{ padding: '12px 20px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>${c.total_cost_usd.toFixed(3)}</td>
                  <td style={{ padding: '12px 20px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => navigate(`/cassettes/${c.id}`)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 4,
                          padding: '4px 10px', background: 'var(--bg-raised)',
                          border: '1px solid var(--border)', borderRadius: 6,
                          color: 'var(--text-2)', fontSize: 12, cursor: 'pointer',
                          fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent)'; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-2)'; }}
                      >
                        <Eye size={12} /> View
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: '48px 20px', textAlign: 'center' }}>
                    {search ? (
                      <div style={{ color: 'var(--text-3)', fontSize: 14 }}>No cassettes match "{search}"</div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
                        <div style={{
                          width: 48, height: 48, borderRadius: 12,
                          background: 'var(--accent-glow)', border: '1px solid var(--accent)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}>
                          <Upload size={20} color="var(--accent)" />
                        </div>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>No cassettes yet</div>
                          <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 16, maxWidth: 320 }}>
                            Upload your first cassette to start tracking agent performance.
                          </div>
                        </div>
                        <button
                          onClick={e => { e.stopPropagation(); setShowUpload(true); }}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 6,
                            padding: '8px 18px',
                            background: 'linear-gradient(135deg, #a78bfa, #8b5cf6)',
                            border: 'none', borderRadius: 8,
                            color: 'white', fontSize: 13, fontWeight: 600,
                            cursor: 'pointer', fontFamily: 'var(--font-sans)',
                          }}
                        >
                          <Upload size={13} /> Upload Cassette
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showUpload && projectId && (
        <UploadCassetteModal
          projectId={projectId}
          onClose={() => setShowUpload(false)}
          onUploaded={() => { refetch(); addToast({ type: 'success', text: 'Cassette uploaded!' }); }}
          onError={msg => addToast({ type: 'error', text: msg })}
        />
      )}
    </Layout>
  );
}
