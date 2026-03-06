import { Component } from 'react';
import type { ReactNode, ErrorInfo } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          background: 'var(--bg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-sans)',
        }}>
          <div style={{
            textAlign: 'center',
            maxWidth: 400,
            padding: 40,
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 16,
            boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
          }}>
            <div style={{
              width: 48, height: 48, borderRadius: 12,
              background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 20px',
            }}>
              <AlertTriangle size={22} color="var(--red)" />
            </div>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text)', margin: '0 0 8px' }}>
              Something went wrong
            </h2>
            <p style={{ fontSize: 13, color: 'var(--text-3)', margin: '0 0 24px', lineHeight: 1.5 }}>
              An unexpected error occurred. Please reload the page to try again.
            </p>
            <button
              onClick={this.handleReload}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                padding: '10px 24px',
                background: 'linear-gradient(135deg, #a78bfa, #8b5cf6)',
                border: 'none', borderRadius: 10,
                color: 'white', fontSize: 13, fontWeight: 600,
                cursor: 'pointer', fontFamily: 'var(--font-sans)',
              }}
            >
              <RefreshCw size={14} /> Reload
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
