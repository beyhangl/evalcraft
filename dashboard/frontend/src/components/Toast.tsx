import { useEffect, useState } from 'react';
import { CheckCircle, AlertCircle, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  text: string;
}

interface ToastProps {
  messages: ToastMessage[];
  onRemove: (id: string) => void;
}

export default function Toast({ messages, onRemove }: ToastProps) {
  return (
    <div style={{
      position: 'fixed',
      bottom: 24,
      right: 24,
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      {messages.map(msg => (
        <ToastItem key={msg.id} msg={msg} onRemove={onRemove} />
      ))}
    </div>
  );
}

function ToastItem({ msg, onRemove }: { msg: ToastMessage; onRemove: (id: string) => void }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    requestAnimationFrame(() => setVisible(true));
    const t = setTimeout(() => {
      setVisible(false);
      setTimeout(() => onRemove(msg.id), 300);
    }, 3000);
    return () => clearTimeout(t);
  }, [msg.id, onRemove]);

  const colors = {
    success: { bg: 'rgba(52,211,153,0.1)', border: 'rgba(52,211,153,0.3)', icon: '#34d399' },
    error:   { bg: 'rgba(248,113,113,0.1)', border: 'rgba(248,113,113,0.3)', icon: '#f87171' },
    info:    { bg: 'rgba(167,139,250,0.1)', border: 'rgba(167,139,250,0.3)', icon: '#a78bfa' },
  }[msg.type];

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '10px 14px',
      background: colors.bg,
      border: `1px solid ${colors.border}`,
      borderRadius: 10,
      backdropFilter: 'blur(12px)',
      fontSize: 13,
      color: 'var(--text)',
      boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
      transform: visible ? 'translateX(0)' : 'translateX(120%)',
      opacity: visible ? 1 : 0,
      transition: 'all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
      minWidth: 240,
      maxWidth: 360,
    }}>
      {msg.type === 'success' ? <CheckCircle size={15} color={colors.icon} /> : <AlertCircle size={15} color={colors.icon} />}
      <span style={{ flex: 1 }}>{msg.text}</span>
      <button
        onClick={() => onRemove(msg.id)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 0, display: 'flex' }}
      >
        <X size={14} />
      </button>
    </div>
  );
}
