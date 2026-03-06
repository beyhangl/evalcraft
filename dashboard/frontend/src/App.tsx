import { useState, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import ErrorBoundary from './components/ErrorBoundary';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Cassettes from './pages/Cassettes';
import CassetteDetail from './pages/CassetteDetail';
import GoldenSets from './pages/GoldenSets';
import GoldenSetDetail from './pages/GoldenSetDetail';
import Regressions from './pages/Regressions';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';
import Toast from './components/Toast';
import type { ToastMessage } from './components/Toast';

function AppRoutes() {
  const { user, isLoading, logout } = useAuth();
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback((msg: Omit<ToastMessage, 'id'>) => {
    setToasts(prev => [...prev, { ...msg, id: crypto.randomUUID() }]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  if (isLoading) {
    return (
      <div style={{
        minHeight: '100vh', background: 'var(--bg)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <div style={{ color: 'var(--text-3)', fontSize: 14 }}>Loading…</div>
      </div>
    );
  }

  return (
    <>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" /> : <Login />} />
        {!user ? (
          <Route path="*" element={<Navigate to="/login" />} />
        ) : (
          <>
            <Route path="/" element={<Dashboard onLogout={logout} addToast={addToast} />} />
            <Route path="/cassettes" element={<Cassettes onLogout={logout} addToast={addToast} />} />
            <Route path="/cassettes/:id" element={<CassetteDetail onLogout={logout} addToast={addToast} />} />
            <Route path="/golden-sets" element={<GoldenSets onLogout={logout} addToast={addToast} />} />
            <Route path="/golden-sets/:id" element={<GoldenSetDetail onLogout={logout} addToast={addToast} />} />
            <Route path="/regressions" element={<Regressions onLogout={logout} addToast={addToast} />} />
            <Route path="/analytics" element={<Analytics onLogout={logout} addToast={addToast} />} />
            <Route path="/settings" element={<Settings onLogout={logout} addToast={addToast} />} />
            <Route path="*" element={<Navigate to="/" />} />
          </>
        )}
      </Routes>
      <Toast messages={toasts} onRemove={removeToast} />
    </>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
