import { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import Layout from '../components/Layout';
import MetricCard from '../components/MetricCard';
import { mockAnalytics, mockHeatmap } from '../data/mock';
import { Activity, DollarSign, Clock, Zap } from 'lucide-react';
import type { ToastMessage } from '../components/Toast';

interface AnalyticsProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

const CustomTooltip = ({ active, payload, label, unit }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
      <div style={{ color: 'var(--text-3)', marginBottom: 4 }}>Day {label}</div>
      <div style={{ color: 'var(--accent)', fontWeight: 600 }}>{payload[0].value.toLocaleString()}{unit}</div>
    </div>
  );
};

const maxHeat = 60;

export default function Analytics({ onLogout, addToast: _addToast }: AnalyticsProps) {
  const [range, setRange] = useState<'7d' | '30d' | '90d'>('30d');

  const sliceData = (data: any[]) => {
    if (range === '7d') return data.slice(-7);
    if (range === '90d') return [...data, ...data, ...data];
    return data;
  };

  const charts = [
    { title: 'Tokens / Day', data: sliceData(mockAnalytics.tokens), color: 'var(--accent)', unit: '', key: 'Tokens' },
    { title: 'Cost / Day ($)', data: sliceData(mockAnalytics.cost), color: 'var(--cyan)', unit: '$', key: 'Cost' },
    { title: 'Avg Latency (ms)', data: sliceData(mockAnalytics.latency), color: 'var(--orange)', unit: 'ms', key: 'Latency' },
  ];

  return (
    <Layout title="Analytics" onLogout={onLogout}>
      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <MetricCard label="Total Tokens" value="2.4M" sub="last 30 days" icon={<Zap size={16} />} accentColor="var(--accent)" />
        <MetricCard label="Total Cost" value="$48.31" sub="↑ 12% vs prev month" subColor="var(--orange)" icon={<DollarSign size={16} />} accentColor="var(--cyan)" />
        <MetricCard label="Avg Latency" value="1,340ms" sub="↓ 80ms vs baseline" subColor="var(--green)" icon={<Clock size={16} />} accentColor="var(--orange)" />
        <MetricCard label="Total Runs" value="4,821" sub="89% pass rate" subColor="var(--green)" icon={<Activity size={16} />} accentColor="var(--green)" />
      </div>

      {/* Date range */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, justifyContent: 'flex-end' }}>
        {(['7d', '30d', '90d'] as const).map(r => (
          <button
            key={r}
            onClick={() => setRange(r)}
            style={{
              padding: '6px 14px',
              background: range === r ? 'var(--accent-glow)' : 'var(--bg-card)',
              border: `1px solid ${range === r ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 8,
              color: range === r ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 12, fontWeight: 500, cursor: 'pointer',
              fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
            }}
          >
            {r}
          </button>
        ))}
      </div>

      {/* Line charts */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 28 }}>
        {charts.map(({ title, data, color, unit }) => (
          <div
            key={title}
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', padding: 20,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 14 }}>{title}</div>
            <ResponsiveContainer width="100%" height={140}>
              <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: -28 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="day" tick={{ fill: 'var(--text-3)', fontSize: 10 }} tickLine={false} axisLine={false} interval={Math.ceil(data.length / 6)} />
                <YAxis tick={{ fill: 'var(--text-3)', fontSize: 10 }} tickLine={false} axisLine={false} />
                <Tooltip content={<CustomTooltip unit={unit} />} />
                <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ))}
      </div>

      {/* Tool usage heatmap */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 24, overflowX: 'auto',
      }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>Tool Usage Heatmap</div>
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 20 }}>Call count by tool × day (last 7 days)</div>

        <div style={{ display: 'inline-block', minWidth: 500 }}>
          {/* Days header */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 6, marginLeft: 130 }}>
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => (
              <div key={d} style={{ width: 40, textAlign: 'center', fontSize: 10, color: 'var(--text-3)', fontWeight: 600 }}>{d}</div>
            ))}
          </div>

          {/* Rows */}
          {mockHeatmap.map(({ tool, values }) => (
            <div key={tool} style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
              <div style={{ width: 126, fontSize: 11, color: 'var(--text-2)', fontFamily: 'var(--font-mono)', textAlign: 'right', paddingRight: 10, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {tool}
              </div>
              {values.map(({ day, count }) => {
                const intensity = count / maxHeat;
                const bg = `rgba(167, 139, 250, ${Math.max(0.05, intensity * 0.85)})`;
                return (
                  <div
                    key={day}
                    title={`${tool} · ${day}: ${count} calls`}
                    style={{
                      width: 40, height: 28,
                      background: bg,
                      border: '1px solid rgba(167,139,250,0.1)',
                      borderRadius: 5,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 10, color: intensity > 0.5 ? 'white' : 'var(--text-3)',
                      fontFamily: 'var(--font-mono)',
                      cursor: 'default',
                      transition: 'transform 0.1s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.15)'}
                    onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
                  >
                    {count}
                  </div>
                );
              })}
            </div>
          ))}

          {/* Legend */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 14, marginLeft: 130 }}>
            <span style={{ fontSize: 10, color: 'var(--text-3)' }}>Low</span>
            {[0.1, 0.25, 0.45, 0.65, 0.85].map(i => (
              <div key={i} style={{ width: 16, height: 16, borderRadius: 3, background: `rgba(167,139,250,${i})` }} />
            ))}
            <span style={{ fontSize: 10, color: 'var(--text-3)' }}>High</span>
          </div>
        </div>
      </div>
    </Layout>
  );
}
