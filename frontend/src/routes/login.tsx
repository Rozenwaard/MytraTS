import { createRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { rootRoute } from "./__root";
import { useAuth } from "../store/auth";

export const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
});

function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [staffId, setStaffId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (user) {
    navigate({ to: "/main-afl" });
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(staffId, password);
      navigate({ to: "/main-afl" });
    } catch {
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
          <form onSubmit={handleSubmit}>
            <div className="form-control mb-4">
              <label className="label"><span className="label-text">Табельный номер</span></label>
              <input type="text" className="input input-bordered w-full" value={staffId} onChange={(e) => setStaffId(e.target.value)} />
            </div>
            <div className="form-control mb-6">
              <label className="label"><span className="label-text">Пароль</span></label>
              <input type="password" className="input input-bordered w-full" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            {error && <div className="alert alert-error mb-4"><span>{error}</span></div>}
            <button type="submit" className="btn btn-accent w-full" disabled={loading}>
              {loading ? <span className="loading loading-spinner" /> : "Войти"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

