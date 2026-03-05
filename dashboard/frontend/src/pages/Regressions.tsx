import { useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { AlertTriangle, Clock } from 'lucide-react';
import Layout from '../components/Layout';
import StatusBadge from '../components/StatusBadge';
import { mockRegressions, mockRegressionTrend } from '../data/mock';
import type { ToastMessage } from '../components/Toast';

interface RegressionsProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 14px', fontSize: 12 }}>
      <div style={{ color: 'var(--text-3)', marginBottom: 6 }}>{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.color, fontWeight: 500 }}>{p.name}: {p.value}</div>
      ))}
    </div>
  );
};

export default function Regressions({ onLogout, addToast: _addToast }: RegressionsProps) {
  const [filter, setFilter] = useState<string>('all');

  const filtered = filter === 'all' ? mockRegressions : mockRegressions.filter(r => r.severity === filter);

  return (
    <Layout title="Regressions" onLogout={onLogout}>
      {/* Trend chart */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 24, marginBottom: 24,
      }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>Regression Trend</div>
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 18 }}>Last 14 days by severity</div>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={mockRegressionTrend} margin={{ top: 4, right: 4, bottom: 4, left: -24 }}>
            <defs>
              {[
                { id: 'critical', color: '#f87171' },
                { id: 'high', color: '#fb923c' },
                { id: 'medium', color: '#fbbf24' },
                { id: 'low', color: '#60a5fa' },
              ].map(({ id, color }) => (
                <linearGradient key={id} id={`grad-${id}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <XAxis dataKey="day" tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 12, color: 'var(--text-3)' }} />
            <Area type="monotone" dataKey="critical" stroke="#f87171" fill="url(#grad-critical)" strokeWidth={2} name="Critical" />
            <Area type="monotone" dataKey="high" stroke="#fb923c" fill="url(#grad-high)" strokeWidth={2} name="High" />
            <Area type="monotone" dataKey="medium" stroke="#fbbf24" fill="url(#grad-medium)" strokeWidth={2} name="Medium" />
            <Area type="monotone" dataKey="low" stroke="#60a5fa" fill="url(#grad-low)" strokeWidth={2} name="Low" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {['all', 'critical', 'high', 'medium', 'low'].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            style={{
              padding: '6px 14px',
              background: filter === s ? (s === 'all' ? 'var(--accent-glow)' : undefined) : 'var(--bg-card)',
              border: `1px solid ${filter === s ? (s === 'all' ? 'var(--accent)' : 'currentColor') : 'var(--border)'}`,
              borderRadius: 8,
              color: filter === s
                ? s === 'all' ? 'var(--accent)' : s === 'critical' ? 'var(--red)' : s === 'high' ? 'var(--orange)' : s === 'medium' ? '#fbbf24' : 'var(--blue)'
                : 'var(--text-2)',
              fontSize: 12, fontWeight: 500, cursor: 'pointer',
              fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
              textTransform: 'capitalize',
            }}
          >
            {s === 'all' ? `All (${mockRegressions.length})` : s}
          </button>
        ))}
      </div>

      {/* Feed */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {filtered.map(reg => {
          const borderColor = reg.severity === 'critical' ? 'rgba(248,113,113,0.25)' : reg.severity === 'high' ? 'rgba(251,146,60,0.25)' : 'var(--border)';
          return (
            <div
              key={reg.id}
              style={{
                background: 'var(--bg-card)',
                border: `1px solid ${borderColor}`,
                borderLeft: `3px solid ${reg.severity === 'critical' ? '#f87171' : reg.severity === 'high' ? '#fb923c' : reg.severity === 'medium' ? '#fbbf24' : '#60a5fa'}`,
                borderRadius: 10,
                padding: '16px 20px',
                transition: 'border-color 0.15s',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flex: 1, minWidth: 0 }}>
                  <AlertTriangle size={15} style={{
                    flexShrink: 0, marginTop: 1,
                    color: reg.severity === 'critical' ? '#f87171' : reg.severity === 'high' ? '#fb923c' : reg.severity === 'medium' ? '#fbbf24' : '#60a5fa',
                  }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                      <StatusBadge status={reg.severity} size="sm" />
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text)', fontWeight: 600 }}>
                        {reg.cassette}
                      </span>
                    </div>
                    <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5, marginBottom: 6 }}>
                      {reg.change}
                    </p>
                    <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-3)' }}>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{reg.model}</span>
                      <span>Pass rate: <span style={{
                        color: reg.passRate < 75 ? 'var(--red)' : reg.passRate < 90 ? 'var(--orange)' : 'var(--green)',
                        fontWeight: 600,
                      }}>{reg.passRate}%</span></span>
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-3)', flexShrink: 0 }}>
                  <Clock size={11} />
                  {reg.ts}
                </div>
              </div>
            </div>
          );
        })}
        {filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: '48px 20px', color: 'var(--text-3)', fontSize: 14 }}>
            No regressions at this severity level
          </div>
        )}
      </div>
    </Layout>
  );
}
