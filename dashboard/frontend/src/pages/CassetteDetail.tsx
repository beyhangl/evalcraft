import { useParams, useNavigate } from 'react-router-dom';
import { ChevronRight, Clock, Zap, DollarSign, Layers } from 'lucide-react';
import Layout from '../components/Layout';
import MetricCard from '../components/MetricCard';
import StatusBadge from '../components/StatusBadge';
import { mockCassetteDetail } from '../data/mock';
import type { ToastMessage } from '../components/Toast';

interface CassetteDetailProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

const spanColors: Record<string, string> = {
  agent: '#a78bfa',
  llm: '#60a5fa',
  tool: '#34d399',
  embed: '#fb923c',
  db: '#22d3ee',
};

export default function CassetteDetail({ onLogout, addToast: _addToast }: CassetteDetailProps) {
  const { id } = useParams();
  const navigate = useNavigate();
  const detail = mockCassetteDetail; // use mock regardless of id
  const totalMs = 2710;

  const headerActions = (
    <StatusBadge status={detail.status} />
  );

  return (
    <Layout title={detail.name} actions={headerActions} onLogout={onLogout}>
      {/* Breadcrumb */}
      <nav style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 24, fontSize: 13, color: 'var(--text-3)' }}>
        <button onClick={() => navigate('/cassettes')} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 13 }}>
          Cassettes
        </button>
        <ChevronRight size={12} />
        <span style={{ color: 'var(--text-2)' }}>{detail.name}</span>
        <ChevronRight size={12} />
        <span style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>#{id}</span>
      </nav>

      {/* Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <MetricCard label="Total Spans" value={detail.totalSpans} sub="12 operations traced" icon={<Layers size={16} />} accentColor="var(--accent)" />
        <MetricCard label="Duration" value={detail.duration} sub="Wall-clock time" icon={<Clock size={16} />} accentColor="var(--cyan)" />
        <MetricCard label="Tokens" value={detail.tokens.toLocaleString()} sub={detail.model} icon={<Zap size={16} />} accentColor="var(--blue)" />
        <MetricCard label="Cost" value={`$${detail.cost.toFixed(4)}`} sub="Estimated" icon={<DollarSign size={16} />} accentColor="var(--orange)" />
      </div>

      {/* Span Timeline */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 24, marginBottom: 20,
      }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 18 }}>Span Timeline</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {detail.spans.map(span => {
            const left = (span.start / totalMs) * 100;
            const width = Math.max(((span.end - span.start) / totalMs) * 100, 2);
            const color = spanColors[span.type] ?? '#71717a';
            return (
              <div key={span.id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 160, fontSize: 11, color: 'var(--text-2)',
                  fontFamily: 'var(--font-mono)', paddingLeft: span.depth * 16,
                  flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {span.name}
                </div>
                <div style={{ flex: 1, position: 'relative', height: 20 }}>
                  <div style={{ position: 'absolute', inset: '4px 0', background: 'var(--border-subtle)', borderRadius: 4 }} />
                  <div style={{
                    position: 'absolute',
                    left: `${left}%`,
                    width: `${width}%`,
                    top: 2, bottom: 2,
                    background: color,
                    borderRadius: 4,
                    opacity: 0.85,
                    cursor: 'default',
                    transition: 'opacity 0.15s',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
                  onMouseLeave={e => (e.currentTarget.style.opacity = '0.85')}
                  title={`${span.start}ms – ${span.end}ms (${span.end - span.start}ms)`}
                  />
                </div>
                <div style={{ width: 50, fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textAlign: 'right', flexShrink: 0 }}>
                  {span.end - span.start}ms
                </div>
              </div>
            );
          })}
        </div>
        {/* Legend */}
        <div style={{ display: 'flex', gap: 16, marginTop: 16, flexWrap: 'wrap' }}>
          {Object.entries(spanColors).map(([type, color]) => (
            <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-3)' }}>
              <div style={{ width: 10, height: 10, borderRadius: 3, background: color, flexShrink: 0 }} />
              {type}
            </div>
          ))}
        </div>
      </div>

      {/* Tool calls */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 24, marginBottom: 20,
      }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 16 }}>Tool Sequence</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {detail.toolCalls.map((tc, i) => (
            <div key={tc.id} style={{
              display: 'flex', gap: 14,
              padding: 16,
              background: 'var(--bg-raised)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 10,
            }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%',
                background: 'var(--accent-glow)', border: '1px solid var(--accent)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 600, color: 'var(--accent)',
                flexShrink: 0, marginTop: 2,
              }}>
                {i + 1}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--green)', fontWeight: 600 }}>
                    {tc.name}()
                  </span>
                  <span style={{
                    fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)',
                    background: 'var(--border-subtle)', padding: '2px 8px', borderRadius: 100,
                  }}>
                    {tc.latency}
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  {[{ label: 'Input', val: tc.input }, { label: 'Output', val: tc.output }].map(({ label, val }) => (
                    <div key={label}>
                      <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 600, letterSpacing: '0.06em', marginBottom: 4, textTransform: 'uppercase' }}>{label}</div>
                      <pre style={{
                        fontSize: 11, color: 'var(--text-2)', fontFamily: 'var(--font-mono)',
                        background: 'var(--bg-code)', border: '1px solid var(--border-subtle)',
                        borderRadius: 6, padding: '8px 10px', overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                        margin: 0, maxHeight: 80,
                      }}>
                        {val}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Diff view */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 24,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Output Diff</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <span style={{ fontSize: 11, padding: '2px 10px', background: 'rgba(52,211,153,0.1)', borderRadius: 100, color: 'var(--green)', fontWeight: 500 }}>Expected</span>
            <span style={{ fontSize: 11, padding: '2px 10px', background: 'rgba(248,113,113,0.1)', borderRadius: 100, color: 'var(--red)', fontWeight: 500 }}>Actual</span>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          {[
            { label: 'Expected', content: detail.expectedOutput, color: 'rgba(52,211,153,0.08)', border: 'rgba(52,211,153,0.2)' },
            { label: 'Actual', content: detail.actualOutput, color: 'rgba(248,113,113,0.08)', border: 'rgba(248,113,113,0.2)' },
          ].map(({ label, content, color, border }) => (
            <div key={label}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
              <pre style={{
                fontFamily: 'var(--font-mono)', fontSize: 12,
                background: color, border: `1px solid ${border}`,
                borderRadius: 8, padding: '14px', overflow: 'auto',
                color: 'var(--text-2)', margin: 0, lineHeight: 1.6,
              }}>
                {content}
              </pre>
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
