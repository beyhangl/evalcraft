import { useState, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Cassettes from './pages/Cassettes';
import CassetteDetail from './pages/CassetteDetail';
import GoldenSets from './pages/GoldenSets';
import Regressions from './pages/Regressions';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';
import Toast from './components/Toast';
import type { ToastMessage } from './components/Toast';

export default function App() {
  const [authed, setAuthed] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback((msg: Omit<ToastMessage, 'id'>) => {
    setToasts(prev => [...prev, { ...msg, id: crypto.randomUUID() }]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const onLogin = () => setAuthed(true);
  const onLogout = () => setAuthed(false);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={authed ? <Navigate to="/" /> : <Login onLogin={onLogin} />} />
        {!authed ? (
          <Route path="*" element={<Navigate to="/login" />} />
        ) : (
          <>
            <Route path="/" element={<Dashboard onLogout={onLogout} addToast={addToast} />} />
            <Route path="/cassettes" element={<Cassettes onLogout={onLogout} addToast={addToast} />} />
            <Route path="/cassettes/:id" element={<CassetteDetail onLogout={onLogout} addToast={addToast} />} />
            <Route path="/golden-sets" element={<GoldenSets onLogout={onLogout} addToast={addToast} />} />
            <Route path="/regressions" element={<Regressions onLogout={onLogout} addToast={addToast} />} />
            <Route path="/analytics" element={<Analytics onLogout={onLogout} addToast={addToast} />} />
            <Route path="/settings" element={<Settings onLogout={onLogout} addToast={addToast} />} />
            <Route path="*" element={<Navigate to="/" />} />
          </>
        )}
      </Routes>
      <Toast messages={toasts} onRemove={removeToast} />
    </BrowserRouter>
  );
}
