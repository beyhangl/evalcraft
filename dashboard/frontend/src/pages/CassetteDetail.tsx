import { useParams, useNavigate } from 'react-router-dom';
import { ChevronRight, Clock, Zap, DollarSign, Layers } from 'lucide-react';
import Layout from '../components/Layout';
import MetricCard from '../components/MetricCard';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { ToastMessage } from '../components/Toast';
import type { CassetteDetail as CassetteDetailType } from '../services/api';

interface CassetteDetailProps {
  onLogout: () => void;
  addToast: (msg: Omit<ToastMessage, 'id'>) => void;
}

const spanKindColors: Record<string, string> = {
  LLM_REQUEST: '#60a5fa',
  LLM_RESPONSE: '#60a5fa',
  TOOL_CALL: '#34d399',
  TOOL_RESULT: '#34d399',
  AGENT_STEP: '#a78bfa',
  USER_INPUT: '#fb923c',
  AGENT_OUTPUT: '#22d3ee',
};

interface Span {
  id: string;
  name: string;
  kind: string;
  timestamp: string;
  duration_ms: number;
  input?: string;
  output?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  tool_result?: string;
  parent_id?: string;
}

export default function CassetteDetail({ onLogout, addToast: _addToast }: CassetteDetailProps) {
  const { id } = useParams();
  const navigate = useNavigate();

  const { data: detail, loading, error } = useApi<CassetteDetailType>(
    () => id ? api.getCassette(id) : Promise.reject(new Error('No ID')),
    [id],
  );

  if (loading) {
    return (
      <Layout title="Cassette Detail" onLogout={onLogout}>
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-3)', fontSize: 14 }}>Loading…</div>
      </Layout>
    );
  }

  if (error || !detail) {
    return (
      <Layout title="Cassette Detail" onLogout={onLogout}>
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--red)', fontSize: 14 }}>{error || 'Not found'}</div>
      </Layout>
    );
  }

  const spans: Span[] = detail.raw_data?.spans as Span[] ?? [];
  const totalMs = detail.total_duration_ms || 1;
  const fmtDuration = (ms: number) => ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;

  // Build tool calls from spans
  const toolCalls = spans.filter(s => s.kind === 'TOOL_CALL');

  // Calculate depths from parent_id
  const depthMap = new Map<string, number>();
  for (const s of spans) {
    if (!s.parent_id) depthMap.set(s.id, 0);
    else depthMap.set(s.id, (depthMap.get(s.parent_id) ?? 0) + 1);
  }

  // Convert timestamps to relative ms for timeline
  const baseTime = spans.length > 0 ? new Date(spans[0].timestamp).getTime() : 0;

  return (
    <Layout title={detail.name} onLogout={onLogout}>
      {/* Breadcrumb */}
      <nav style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 24, fontSize: 13, color: 'var(--text-3)' }}>
        <button onClick={() => navigate('/cassettes')} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 13 }}>
          Cassettes
        </button>
        <ChevronRight size={12} />
        <span style={{ color: 'var(--text-2)' }}>{detail.name}</span>
        <ChevronRight size={12} />
        <span style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>#{id?.slice(0, 8)}</span>
      </nav>

      {/* Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <MetricCard label="Total Spans" value={String(spans.length)} sub={`${detail.llm_call_count} LLM · ${detail.tool_call_count} tool`} icon={<Layers size={16} />} accentColor="var(--accent)" />
        <MetricCard label="Duration" value={fmtDuration(detail.total_duration_ms)} sub="Wall-clock time" icon={<Clock size={16} />} accentColor="var(--cyan)" />
        <MetricCard label="Tokens" value={detail.total_tokens.toLocaleString()} sub={`${detail.agent_name} · ${detail.framework}`} icon={<Zap size={16} />} accentColor="var(--blue)" />
        <MetricCard label="Cost" value={`$${detail.total_cost_usd.toFixed(4)}`} sub="Estimated" icon={<DollarSign size={16} />} accentColor="var(--orange)" />
      </div>

      {/* Span Timeline */}
      {spans.length > 0 && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 24, marginBottom: 20,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 18 }}>Span Timeline</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {spans.map(span => {
              const startMs = new Date(span.timestamp).getTime() - baseTime;
              const left = (startMs / totalMs) * 100;
              const width = Math.max((span.duration_ms / totalMs) * 100, 2);
              const color = spanKindColors[span.kind] ?? '#71717a';
              const depth = depthMap.get(span.id) ?? 0;
              return (
                <div key={span.id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 160, fontSize: 11, color: 'var(--text-2)',
                    fontFamily: 'var(--font-mono)', paddingLeft: depth * 16,
                    flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {span.name}
                  </div>
                  <div style={{ flex: 1, position: 'relative', height: 20 }}>
                    <div style={{ position: 'absolute', inset: '4px 0', background: 'var(--border-subtle)', borderRadius: 4 }} />
                    <div style={{
                      position: 'absolute',
                      left: `${Math.min(left, 98)}%`,
                      width: `${Math.min(width, 100 - left)}%`,
                      top: 2, bottom: 2,
                      background: color,
                      borderRadius: 4,
                      opacity: 0.85,
                    }}
                    title={`${span.kind} · ${span.duration_ms}ms`}
                    />
                  </div>
                  <div style={{ width: 50, fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textAlign: 'right', flexShrink: 0 }}>
                    {span.duration_ms}ms
                  </div>
                </div>
              );
            })}
          </div>
          {/* Legend */}
          <div style={{ display: 'flex', gap: 16, marginTop: 16, flexWrap: 'wrap' }}>
            {Object.entries(spanKindColors).map(([kind, color]) => (
              <div key={kind} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-3)' }}>
                <div style={{ width: 10, height: 10, borderRadius: 3, background: color, flexShrink: 0 }} />
                {kind}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tool calls */}
      {toolCalls.length > 0 && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 24, marginBottom: 20,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 16 }}>Tool Calls</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {toolCalls.map((tc, i) => (
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
                      {tc.tool_name ?? tc.name}()
                    </span>
                    <span style={{
                      fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)',
                      background: 'var(--border-subtle)', padding: '2px 8px', borderRadius: 100,
                    }}>
                      {tc.duration_ms}ms
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    {[{ label: 'Input', val: tc.tool_args ? JSON.stringify(tc.tool_args, null, 2) : tc.input ?? '' }, { label: 'Output', val: tc.tool_result ?? tc.output ?? '' }].map(({ label, val }) => (
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
      )}

      {/* Output Diff */}
      {(detail.input_text || detail.output_text) && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 24,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 16 }}>Input / Output</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {[
              { label: 'Input', content: detail.input_text, color: 'rgba(96,165,250,0.08)', border: 'rgba(96,165,250,0.2)' },
              { label: 'Output', content: detail.output_text, color: 'rgba(52,211,153,0.08)', border: 'rgba(52,211,153,0.2)' },
            ].map(({ label, content, color, border }) => (
              <div key={label}>
                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
                <pre style={{
                  fontFamily: 'var(--font-mono)', fontSize: 12,
                  background: color, border: `1px solid ${border}`,
                  borderRadius: 8, padding: '14px', overflow: 'auto',
                  color: 'var(--text-2)', margin: 0, lineHeight: 1.6,
                  maxHeight: 200,
                }}>
                  {content}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </Layout>
  );
}
