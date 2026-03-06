import { useNavigate } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity, DollarSign, AlertTriangle, TrendingUp, Upload, Plus } from 'lucide-react';
import Layout from '../components/Layout';
import MetricCard from '../components/MetricCard';
import { useAuth } from '../context/AuthContext';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { ToastMessage } from '../components/Toast';
import type { CassetteListItem, TrendsResponse } from '../services/api';

interface DashboardProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 8, padding: '8px 12px', fontSize: 12,
    }}>
      <div style={{ color: 'var(--text-3)', marginBottom: 4 }}>{label}</div>
      <div style={{ color: 'var(--accent)', fontWeight: 600 }}>{payload[0].value.toLocaleString()} tokens</div>
    </div>
  );
};

export default function Dashboard({ onLogout, addToast }: DashboardProps) {
  const navigate = useNavigate();
  const { currentProject } = useAuth();
  const projectId = currentProject?.id ?? '';

  const { data: cassettes } = useApi<CassetteListItem[]>(
    () => projectId ? api.listCassettes(projectId) : Promise.resolve([]),
    [projectId],
  );

  const { data: trends } = useApi<TrendsResponse>(
    () => projectId ? api.getTrends(projectId, 30) : Promise.resolve({ project_id: '', points: [] }),
    [projectId],
  );

  const points = trends?.points ?? [];
  const totalTokens = points.reduce((s, p) => s + p.total_tokens, 0);
  const totalCost = points.reduce((s, p) => s + p.total_cost_usd, 0);
  const totalRuns = points.reduce((s, p) => s + p.cassette_count, 0);
  const recentCassettes = cassettes?.slice(0, 8) ?? [];

  const actions = (
    <>
      <button
        onClick={() => addToast({ type: 'success', text: 'Upload modal would open here' })}
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
        <Upload size={13} /> Upload Cassette
      </button>
      <button
        onClick={() => addToast({ type: 'success', text: 'Golden set created!' })}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '6px 14px',
          background: 'linear-gradient(135deg, #a78bfa, #8b5cf6)',
          border: 'none', borderRadius: 8,
          color: 'white', fontSize: 13, fontWeight: 600,
          cursor: 'pointer', fontFamily: 'var(--font-sans)',
        }}
      >
        <Plus size={13} /> Golden Set
      </button>
    </>
  );

  const fmtDuration = (ms: number) => ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;

  return (
    <Layout title="Dashboard" actions={actions} onLogout={onLogout}>
      {/* Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <MetricCard
          label="Total Runs"
          value={totalRuns.toLocaleString()}
          sub={`${points.length} day trend`}
          icon={<Activity size={16} />}
          accentColor="var(--accent)"
        />
        <MetricCard
          label="Total Tokens"
          value={totalTokens.toLocaleString()}
          sub="last 30 days"
          icon={<TrendingUp size={16} />}
          accentColor="var(--green)"
        />
        <MetricCard
          label="Cost This Month"
          value={`$${totalCost.toFixed(2)}`}
          sub={`${totalRuns} runs`}
          subColor="var(--text-3)"
          icon={<DollarSign size={16} />}
          accentColor="var(--cyan)"
        />
        <MetricCard
          label="Cassettes"
          value={String(cassettes?.length ?? 0)}
          sub="in project"
          icon={<AlertTriangle size={16} />}
          accentColor="var(--orange)"
        />
      </div>

      {/* Chart + Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 16, marginBottom: 28 }}>
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 24,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Token Usage Trend</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>Daily total tokens</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={points} margin={{ top: 4, right: 4, bottom: 4, left: -24 }}>
              <XAxis dataKey="date" tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} interval={4} />
              <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Line type="monotone" dataKey="total_tokens" stroke="var(--accent)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 24,
          display: 'flex', flexDirection: 'column', gap: 20,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Summary</div>
          {[
            { label: 'Total runs', value: totalRuns.toLocaleString(), color: 'var(--accent)' },
            { label: 'Total tokens', value: totalTokens.toLocaleString(), color: 'var(--cyan)' },
            { label: 'Total cost', value: `$${totalCost.toFixed(2)}`, color: 'var(--blue)' },
            { label: 'Avg latency', value: points.length > 0 ? fmtDuration(points.reduce((s, p) => s + p.total_duration_ms, 0) / points.length) : '—', color: 'var(--orange)' },
            { label: 'Cassettes', value: String(cassettes?.length ?? 0), color: 'var(--green)' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{label}</span>
              <span style={{ fontSize: 14, fontWeight: 600, color, fontFamily: 'var(--font-mono)' }}>{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Cassettes */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden',
      }}>
        <div style={{ padding: '18px 24px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Recent Cassettes</div>
          <button
            onClick={() => navigate('/cassettes')}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--accent)', fontSize: 12, fontWeight: 500, fontFamily: 'var(--font-sans)',
            }}
          >
            View all →
          </button>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                {['Cassette', 'Agent', 'Duration', 'Tokens', 'Cost', 'Framework', 'Time'].map(h => (
                  <th key={h} style={{
                    padding: '10px 24px', textAlign: 'left',
                    fontSize: 11, fontWeight: 600, color: 'var(--text-3)',
                    letterSpacing: '0.06em', textTransform: 'uppercase',
                    whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recentCassettes.map((c, i) => (
                <tr
                  key={c.id}
                  onClick={() => navigate(`/cassettes/${c.id}`)}
                  style={{
                    borderBottom: i < recentCassettes.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                    cursor: 'pointer', transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-raised)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '12px 24px', fontSize: 13, color: 'var(--text)', fontFamily: 'var(--font-mono)', fontWeight: 500 }}>
                    {c.name}
                  </td>
                  <td style={{ padding: '12px 24px', fontSize: 12, color: 'var(--text-2)' }}>{c.agent_name}</td>
                  <td style={{ padding: '12px 24px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{fmtDuration(c.total_duration_ms)}</td>
                  <td style={{ padding: '12px 24px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{c.total_tokens.toLocaleString()}</td>
                  <td style={{ padding: '12px 24px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>${c.total_cost_usd.toFixed(3)}</td>
                  <td style={{ padding: '12px 24px', fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{c.framework}</td>
                  <td style={{ padding: '12px 24px', fontSize: 12, color: 'var(--text-3)' }}>{new Date(c.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
              {recentCassettes.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-3)', fontSize: 14 }}>
                    No cassettes yet
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
