import type { ReactNode } from 'react';
import Sidebar from './Sidebar';

interface LayoutProps {
  children: ReactNode;
  title: string;
  actions?: ReactNode;
  onLogout: () => void;
}

export default function Layout({ children, title, actions, onLogout }: LayoutProps) {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg)' }}>
      <Sidebar onLogout={onLogout} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Header */}
        <header style={{
          height: 56,
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 28px',
          background: 'var(--bg)',
          position: 'sticky',
          top: 0,
          zIndex: 10,
          backdropFilter: 'blur(8px)',
          flexShrink: 0,
        }}>
          <h1 style={{
            fontSize: 15,
            fontWeight: 600,
            color: 'var(--text)',
            letterSpacing: '-0.01em',
          }}>
            {title}
          </h1>
          {actions && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {actions}
            </div>
          )}
        </header>

        {/* Main */}
        <main style={{ flex: 1, padding: '28px', overflow: 'auto' }}>
          {children}
        </main>
      </div>
    </div>
  );
}
