import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, User } from "../api/client";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (staffId: string, password: string) => Promise<{ changePassword: boolean }>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<{ user: User | null }>("/api/me")
      .then((data) => setUser(data.user))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (staffId: string, password: string) => {
    const data = await api<{
      ok: boolean;
      change_password: boolean;
      full_name: string;
      role: User["role"];
    }>("/api/login", {
      method: "POST",
      body: JSON.stringify({ staff_id: staffId, password }),
    });
    if (data.ok) {
      const me = await api<{ user: User }>("/api/me");
      setUser(me.user);
    }
    return { changePassword: data.change_password };
  }, []);

  const logout = useCallback(async () => {
    await api("/api/logout", { method: "POST" });
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
