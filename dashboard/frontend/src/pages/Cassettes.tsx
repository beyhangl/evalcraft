import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Upload, ChevronUp, ChevronDown, Trash2, Eye } from 'lucide-react';
import Layout from '../components/Layout';
import StatusBadge from '../components/StatusBadge';
import { mockCassettes } from '../data/mock';
import type { ToastMessage } from '../components/Toast';

type SortKey = 'name' | 'date' | 'tokens' | 'cost' | 'runs';
type SortDir = 'asc' | 'desc';

interface CassettesProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

export default function Cassettes({ onLogout, addToast }: CassettesProps) {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<string>('all');
  const [sortKey, setSortKey] = useState<SortKey>('date');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [cassettes, setCassettes] = useState(mockCassettes);

  const filtered = useMemo(() => {
    let list = cassettes.filter(c => {
      if (search && !c.name.toLowerCase().includes(search.toLowerCase())) return false;
      if (filter !== 'all' && c.status !== filter) return false;
      return true;
    });
    list = [...list].sort((a, b) => {
      const av = a[sortKey as keyof typeof a];
      const bv = b[sortKey as keyof typeof b];
      const cmp = typeof av === 'string' ? (av as string).localeCompare(bv as string) : (av as number) - (bv as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [cassettes, search, filter, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const SortIcon = ({ k }: { k: SortKey }) => sortKey === k
    ? (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)
    : <ChevronDown size={12} style={{ opacity: 0.3 }} />;

  const deleteRow = (id: string) => {
    setCassettes(prev => prev.filter(c => c.id !== id));
    addToast({ type: 'success', text: 'Cassette deleted' });
  };

  const actions = (
    <button
      onClick={() => addToast({ type: 'info', text: 'Upload cassette dialog would open here' })}
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

  return (
    <Layout title="Cassettes" actions={actions} onLogout={onLogout}>
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{
          flex: 1, minWidth: 220,
          position: 'relative',
        }}>
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
        {['all', 'pass', 'fail', 'running', 'pending'].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            style={{
              padding: '7px 14px',
              background: filter === s ? 'var(--accent-glow)' : 'var(--bg-card)',
              border: `1px solid ${filter === s ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 9,
              color: filter === s ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
              textTransform: 'capitalize',
              transition: 'all 0.15s',
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Table */}
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {([
                  { label: 'Name', key: 'name' },
                  { label: 'Status', key: null },
                  { label: 'Date', key: 'date' },
                  { label: 'Tokens', key: 'tokens' },
                  { label: 'Cost', key: 'cost' },
                  { label: 'Runs', key: 'runs' },
                  { label: 'Actions', key: null },
                ] as { label: string; key: SortKey | null }[]).map(({ label, key }) => (
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
                  <td style={{ padding: '12px 20px' }}><StatusBadge status={c.status} size="sm" /></td>
                  <td style={{ padding: '12px 20px', fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{c.date}</td>
                  <td style={{ padding: '12px 20px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{c.tokens.toLocaleString()}</td>
                  <td style={{ padding: '12px 20px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>${c.cost.toFixed(3)}</td>
                  <td style={{ padding: '12px 20px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{c.runs}</td>
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
                      <button
                        onClick={() => deleteRow(c.id)}
                        style={{
                          display: 'flex', alignItems: 'center',
                          padding: '4px 8px', background: 'none',
                          border: '1px solid var(--border)', borderRadius: 6,
                          color: 'var(--text-3)', cursor: 'pointer',
                          transition: 'all 0.15s',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(248,113,113,0.4)'; e.currentTarget.style.color = 'var(--red)'; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-3)'; }}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-3)', fontSize: 14 }}>
                    No cassettes found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  );
}
