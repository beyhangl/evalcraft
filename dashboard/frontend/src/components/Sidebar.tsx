import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Layers, Target, AlertTriangle,
  BarChart3, Settings, LogOut, Zap, ChevronRight,
  Menu, X,
} from 'lucide-react';
import { useState } from 'react';
import { mockUser } from '../data/mock';

const navItems = [
  { to: '/',             label: 'Dashboard',   icon: LayoutDashboard },
  { to: '/cassettes',    label: 'Cassettes',   icon: Layers },
  { to: '/golden-sets',  label: 'Golden Sets', icon: Target },
  { to: '/regressions',  label: 'Regressions', icon: AlertTriangle },
  { to: '/analytics',    label: 'Analytics',   icon: BarChart3 },
  { to: '/settings',     label: 'Settings',    icon: Settings },
];

interface SidebarProps {
  onLogout: () => void;
}

export default function Sidebar({ onLogout }: SidebarProps) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = () => {
    onLogout();
    navigate('/login');
  };

  const inner = (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
    }}>
      {/* Logo */}
      <div style={{
        padding: '20px 18px 16px',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
      }}>
        <div style={{
          width: 32,
          height: 32,
          background: 'linear-gradient(135deg, #a78bfa, #60a5fa)',
          borderRadius: 8,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}>
          <Zap size={16} color="white" strokeWidth={2.5} />
        </div>
        <span style={{
          fontSize: 16,
          fontWeight: 700,
          background: 'linear-gradient(90deg, #a78bfa, #60a5fa)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          letterSpacing: '-0.01em',
        }}>
          Evalcraft
        </span>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '12px 8px', overflowY: 'auto' }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-3)', letterSpacing: '0.08em', padding: '4px 10px 8px', textTransform: 'uppercase' }}>
          Navigation
        </div>
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            onClick={() => setOpen(false)}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 10px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 500,
              color: isActive ? 'var(--accent)' : 'var(--text-2)',
              background: isActive ? 'var(--accent-glow)' : 'transparent',
              textDecoration: 'none',
              transition: 'all 0.15s',
              marginBottom: 2,
              position: 'relative',
            })}
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <div style={{
                    position: 'absolute',
                    left: 0,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: 3,
                    height: 18,
                    background: 'var(--accent)',
                    borderRadius: '0 3px 3px 0',
                  }} />
                )}
                <Icon size={15} strokeWidth={isActive ? 2.5 : 2} />
                <span style={{ flex: 1 }}>{label}</span>
                {isActive && <ChevronRight size={12} style={{ opacity: 0.5 }} />}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User */}
      <div style={{
        borderTop: '1px solid var(--border-subtle)',
        padding: '12px 8px',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '8px 10px',
          borderRadius: 8,
          marginBottom: 4,
        }}>
          <div style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #a78bfa40, #60a5fa40)',
            border: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--accent)',
            flexShrink: 0,
          }}>
            {mockUser.avatar}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {mockUser.name}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {mockUser.plan} plan
            </div>
          </div>
        </div>
        <button
          onClick={handleLogout}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            width: '100%',
            padding: '7px 10px',
            background: 'none',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            color: 'var(--text-3)',
            fontSize: 12,
            fontWeight: 500,
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.color = 'var(--red)';
            e.currentTarget.style.background = 'rgba(248,113,113,0.08)';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.color = 'var(--text-3)';
            e.currentTarget.style.background = 'none';
          }}
        >
          <LogOut size={13} />
          Sign out
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'none',
          position: 'fixed',
          top: 12,
          left: 12,
          zIndex: 200,
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: 8,
          cursor: 'pointer',
          color: 'var(--text-2)',
        }}
        className="mobile-menu-btn"
      >
        {open ? <X size={18} /> : <Menu size={18} />}
      </button>

      {/* Mobile overlay */}
      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            display: 'none',
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            zIndex: 99,
          }}
          className="mobile-overlay"
        />
      )}

      {/* Desktop sidebar */}
      <aside style={{
        width: 224,
        minWidth: 224,
        height: '100vh',
        background: 'var(--bg-sidebar)',
        borderRight: '1px solid var(--border-subtle)',
        position: 'sticky',
        top: 0,
        overflowY: 'auto',
        flexShrink: 0,
      }}>
        {inner}
      </aside>

      <style>{`
        @media (max-width: 768px) {
          .mobile-menu-btn { display: flex !important; }
          .mobile-overlay { display: block !important; }
        }
      `}</style>
    </>
  );
}
