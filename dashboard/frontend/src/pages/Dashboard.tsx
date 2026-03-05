import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity, DollarSign, AlertTriangle, TrendingUp, Upload, Plus } from 'lucide-react';
import Layout from '../components/Layout';
import MetricCard from '../components/MetricCard';
import StatusBadge from '../components/StatusBadge';
import { mockRuns, mockPassRateSeries } from '../data/mock';
import type { ToastMessage } from '../components/Toast';

interface DashboardProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 8, padding: '8px 12px', fontSize: 12,
    }}>
      <div style={{ color: 'var(--text-3)', marginBottom: 4 }}>Day {label}</div>
      <div style={{ color: 'var(--accent)', fontWeight: 600 }}>{payload[0].value}% pass rate</div>
    </div>
  );
};

export default function Dashboard({ onLogout, addToast }: DashboardProps) {
  const navigate = useNavigate();
  const [showSkeleton] = useState(false);

  const avgPass = Math.round(mockPassRateSeries.reduce((a, b) => a + b.rate, 0) / mockPassRateSeries.length);

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

  return (
    <Layout title="Dashboard" actions={actions} onLogout={onLogout}>
      {/* Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <MetricCard
          label="Total Runs"
          value="4,821"
          sub="↑ 18% vs last week"
          subColor="var(--green)"
          icon={<Activity size={16} />}
          accentColor="var(--accent)"
        />
        <MetricCard
          label="Pass Rate"
          value={`${avgPass}%`}
          sub="↓ 2.4% vs yesterday"
          subColor="var(--red)"
          icon={<TrendingUp size={16} />}
          accentColor="var(--green)"
        />
        <MetricCard
          label="Cost This Month"
          value="$48.31"
          sub="$1.74 today · 62% of budget"
          subColor="var(--text-3)"
          icon={<DollarSign size={16} />}
          accentColor="var(--cyan)"
        />
        <MetricCard
          label="Active Regressions"
          value="7"
          sub="2 critical · 3 high"
          subColor="var(--red)"
          icon={<AlertTriangle size={16} />}
          accentColor="var(--red)"
        />
      </div>

      {/* Chart + Table row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 16, marginBottom: 28 }}>
        {/* Pass rate chart */}
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 24,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Pass Rate Trend</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>30-day rolling average</div>
            </div>
            <div style={{
              fontSize: 11, padding: '3px 10px',
              background: 'var(--accent-glow)', borderRadius: 100,
              color: 'var(--accent)', fontWeight: 500,
            }}>
              {avgPass}% avg
            </div>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={mockPassRateSeries} margin={{ top: 4, right: 4, bottom: 4, left: -24 }}>
              <XAxis dataKey="day" tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} interval={4} />
              <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} domain={[60, 100]} />
              <Tooltip content={<CustomTooltip />} />
              <Line type="monotone" dataKey="rate" stroke="var(--accent)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Quick stats */}
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 24,
          display: 'flex', flexDirection: 'column', gap: 20,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Today at a glance</div>
          {[
            { label: 'Runs today', value: '142', color: 'var(--accent)' },
            { label: 'Tokens used', value: '892K', color: 'var(--cyan)' },
            { label: 'Avg latency', value: '1.4s', color: 'var(--blue)' },
            { label: 'Models used', value: '3', color: 'var(--orange)' },
            { label: 'Cassettes active', value: '24', color: 'var(--green)' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{label}</span>
              <span style={{ fontSize: 14, fontWeight: 600, color, fontFamily: 'var(--font-mono)' }}>{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Runs */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden',
      }}>
        <div style={{ padding: '18px 24px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Recent Runs</div>
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
                {['Cassette', 'Status', 'Duration', 'Tokens', 'Cost', 'Model', 'Time'].map(h => (
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
              {(showSkeleton ? Array(6).fill(null) : mockRuns).map((run, i) => (
                showSkeleton ? (
                  <tr key={i}>
                    {Array(7).fill(null).map((_, j) => (
                      <td key={j} style={{ padding: '12px 24px' }}>
                        <div style={{
                          height: 14, background: 'var(--border)',
                          borderRadius: 4, width: j === 0 ? '60%' : '40%',
                          animation: 'pulse 1.5s ease-in-out infinite',
                        }} />
                      </td>
                    ))}
                  </tr>
                ) : (
                  <tr
                    key={run.id}
                    onClick={() => navigate(`/cassettes/${run.id}`)}
                    style={{
                      borderBottom: i < mockRuns.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                      cursor: 'pointer', transition: 'background 0.1s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-raised)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ padding: '12px 24px', fontSize: 13, color: 'var(--text)', fontFamily: 'var(--font-mono)', fontWeight: 500 }}>
                      {run.cassette}
                    </td>
                    <td style={{ padding: '12px 24px' }}><StatusBadge status={run.status} size="sm" /></td>
                    <td style={{ padding: '12px 24px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{run.duration}</td>
                    <td style={{ padding: '12px 24px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{run.tokens.toLocaleString()}</td>
                    <td style={{ padding: '12px 24px', fontSize: 13, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>${run.cost.toFixed(3)}</td>
                    <td style={{ padding: '12px 24px', fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{run.model}</td>
                    <td style={{ padding: '12px 24px', fontSize: 12, color: 'var(--text-3)' }}>{run.ts}</td>
                  </tr>
                )
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }`}</style>
    </Layout>
  );
}
