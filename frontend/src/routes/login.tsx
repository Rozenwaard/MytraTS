import { createRoute, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { rootRoute } from "./__root";
import { useAuth } from "../store/auth";
import { api } from "../api/client";

interface UserSuggestion {
  full_name: string;
  position: string;
  staff_id: string;
}

export const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
});

function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [surname, setSurname] = useState("");
  const [staffId, setStaffId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<UserSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const searchUsers = useCallback((q: string) => {
    if (debounceRef.current !== null) clearTimeout(debounceRef.current);
    if (q.length < 3) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await api<UserSuggestion[]>(`/api/users/search?q=${encodeURIComponent(q)}`);
        setSuggestions(data);
        setShowSuggestions(data.length > 0);
      } catch {
        setSuggestions([]);
      }
    }, 300);
  }, []);

  const selectUser = (s: UserSuggestion) => {
    setSurname(s.full_name);
    setStaffId(s.staff_id);
    setSuggestions([]);
    setShowSuggestions(false);
  };

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (formRef.current && !formRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!staffId) {
      setError("Выберите пользователя из списка подсказок");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await login(staffId, password);
      navigate({ to: result.changePassword ? "/change-password" : "/dashboard" });
    } catch (err) {
      console.error("Login error:", err);
      setError("Неверный логин или пароль");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[70vh]">
      <div className="card bg-base-100 shadow-xl w-full max-w-md">
        <div className="card-body">
          <h2 className="card-title text-center justify-center mb-2">MYTRA</h2>
          <p className="text-center text-base-content/50 text-sm mb-6">Управление реестрами</p>

          <form ref={formRef} onSubmit={handleSubmit} autoComplete="off">
            <div className="form-control mb-4 relative">
              <label className="label"><span className="label-text">Фамилия</span></label>
              <input
                type="text"
                placeholder="Начните вводить фамилию"
                className="input input-bordered w-full"
                value={surname}
                autoComplete="off"
                onChange={(e) => {
                  setSurname(e.target.value);
                  setStaffId("");
                  searchUsers(e.target.value);
                }}
              />
              {showSuggestions && (
                <div className="absolute top-full left-0 right-0 bg-base-100 border border-base-300 rounded-box shadow-lg z-10">
                  {suggestions.map((s) => (
                    <div
                      key={s.staff_id}
                      className="p-3 hover:bg-base-200 cursor-pointer border-b border-base-200 last:border-b-0"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        selectUser(s);
                      }}
                    >
                      <div className="text-sm font-medium">{s.full_name}</div>
                      <div className="text-xs text-base-content/50">{s.position} • {s.staff_id}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="form-control mb-6">
              <label className="label"><span className="label-text">Пароль</span></label>
              <input
                type="password"
                placeholder="Введите пароль"
                className="input input-bordered w-full"
                value={password}
                autoComplete="current-password"
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error && <div className="alert alert-error mb-4"><span>{error}</span></div>}
            <button type="submit" className="btn btn-accent w-full" disabled={loading}>
              {loading ? <span className="loading loading-spinner" /> : "Войти"}
            </button>
          </form>

          <div className="text-center text-xs text-base-content/30 mt-4">
            Первый вход — используйте табельный номер
          </div>
        </div>
      </div>
    </div>
  );
}


