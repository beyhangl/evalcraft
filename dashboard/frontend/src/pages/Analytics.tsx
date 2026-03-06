import { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import Layout from '../components/Layout';
import MetricCard from '../components/MetricCard';
import { SkeletonCard } from '../components/Skeleton';
import { useAuth } from '../context/AuthContext';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import { Activity, DollarSign, Clock, Zap } from 'lucide-react';
import type { ToastMessage } from '../components/Toast';
import type { TrendsResponse } from '../services/api';

interface AnalyticsProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

const CustomTooltip = ({ active, payload, label, unit }: { active?: boolean; payload?: { value: number }[]; label?: string; unit?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
      <div style={{ color: 'var(--text-3)', marginBottom: 4 }}>{label}</div>
      <div style={{ color: 'var(--accent)', fontWeight: 600 }}>{payload[0].value.toLocaleString()}{unit}</div>
    </div>
  );
};

export default function Analytics({ onLogout }: AnalyticsProps) {
  const { currentProject } = useAuth();
  const projectId = currentProject?.id ?? '';
  const [days, setDays] = useState(30);

  const { data: trends, loading } = useApi<TrendsResponse>(
    () => projectId ? api.getTrends(projectId, days) : Promise.resolve({ project_id: '', points: [] }),
    [projectId, days],
  );

  const points = trends?.points ?? [];
  const totalTokens = points.reduce((s, p) => s + p.total_tokens, 0);
  const totalCost = points.reduce((s, p) => s + p.total_cost_usd, 0);
  const avgLatency = points.length > 0 ? Math.round(points.reduce((s, p) => s + p.total_duration_ms, 0) / points.length) : 0;
  const totalRuns = points.reduce((s, p) => s + p.cassette_count, 0);

  const tokenData = points.map(p => ({ day: p.date, value: p.total_tokens }));
  const costData = points.map(p => ({ day: p.date, value: p.total_cost_usd }));
  const latencyData = points.map(p => ({ day: p.date, value: p.total_duration_ms }));

  const charts = [
    { title: 'Tokens / Day', data: tokenData, color: 'var(--accent)', unit: '' },
    { title: 'Cost / Day ($)', data: costData, color: 'var(--cyan)', unit: '$' },
    { title: 'Avg Latency (ms)', data: latencyData, color: 'var(--orange)', unit: 'ms' },
  ];

  return (
    <Layout title="Analytics" onLogout={onLogout}>
      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <MetricCard label="Total Tokens" value={totalTokens.toLocaleString()} sub={`last ${days} days`} icon={<Zap size={16} />} accentColor="var(--accent)" />
        <MetricCard label="Total Cost" value={`$${totalCost.toFixed(2)}`} sub={`${totalRuns} runs`} icon={<DollarSign size={16} />} accentColor="var(--cyan)" />
        <MetricCard label="Avg Latency" value={`${avgLatency.toLocaleString()}ms`} sub="per cassette" icon={<Clock size={16} />} accentColor="var(--orange)" />
        <MetricCard label="Total Runs" value={totalRuns.toLocaleString()} sub={`${points.length} days`} icon={<Activity size={16} />} accentColor="var(--green)" />
      </div>

      {/* Date range */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, justifyContent: 'flex-end' }}>
        {([{ label: '7d', val: 7 }, { label: '30d', val: 30 }, { label: '90d', val: 90 }] as const).map(r => (
          <button
            key={r.label}
            onClick={() => setDays(r.val)}
            style={{
              padding: '6px 14px',
              background: days === r.val ? 'var(--accent-glow)' : 'var(--bg-card)',
              border: `1px solid ${days === r.val ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 8,
              color: days === r.val ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 12, fontWeight: 500, cursor: 'pointer',
              fontFamily: 'var(--font-sans)', transition: 'all 0.15s',
            }}
          >
            {r.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 28 }}>
          <SkeletonCard height={200} />
          <SkeletonCard height={200} />
          <SkeletonCard height={200} />
        </div>
      ) : (
        /* Line charts */
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
      )}
    </Layout>
  );
}
