import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { api, setToken, setOnUnauth } from '../services/api';
import type { UserResponse, ProjectResponse } from '../services/api';

interface AuthState {
  user: UserResponse | null;
  projects: ProjectResponse[];
  currentProject: ProjectResponse | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, fullName: string, teamName: string) => Promise<string>;
  logout: () => void;
  setCurrentProject: (p: ProjectResponse) => void;
  refreshProjects: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [currentProject, setCurrentProject] = useState<ProjectResponse | null>(null);
  const [isLoading, setIsLoading] = useState(() => !!localStorage.getItem('ec_token'));

  const logout = useCallback(() => {
    setToken(null);
    localStorage.removeItem('ec_token');
    setUser(null);
    setProjects([]);
    setCurrentProject(null);
  }, []);

  // Restore session on mount
  useEffect(() => {
    setOnUnauth(logout);
    const saved = localStorage.getItem('ec_token');
    if (!saved) return;
    setToken(saved);
    api.me()
      .then(async (u) => {
        setUser(u);
        const projs = await api.listProjects();
        setProjects(projs);
        if (projs.length > 0) setCurrentProject(projs[0]);
      })
      .catch(() => {
        localStorage.removeItem('ec_token');
        setToken(null);
      })
      .finally(() => setIsLoading(false));
  }, [logout]);

  const refreshProjects = useCallback(async () => {
    const projs = await api.listProjects();
    setProjects(projs);
    if (projs.length > 0 && !currentProject) setCurrentProject(projs[0]);
  }, [currentProject]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    setToken(res.access_token);
    localStorage.setItem('ec_token', res.access_token);
    const u = await api.me();
    setUser(u);
    const projs = await api.listProjects();
    setProjects(projs);
    if (projs.length > 0) setCurrentProject(projs[0]);
  }, []);

  const signup = useCallback(async (email: string, password: string, fullName: string, teamName: string) => {
    const res = await api.signup(email, password, fullName, teamName);
    setToken(res.access_token);
    localStorage.setItem('ec_token', res.access_token);
    const u = await api.me();
    setUser(u);
    const projs = await api.listProjects();
    setProjects(projs);
    if (projs.length > 0) setCurrentProject(projs[0]);
    return res.access_token;
  }, []);

  return (
    <AuthContext.Provider value={{ user, projects, currentProject, isLoading, login, signup, logout, setCurrentProject, refreshProjects }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
