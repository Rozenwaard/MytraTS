import { createRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { rootRoute } from "../__root";
import { useAuth } from "../../store/auth";
import { api } from "../../api/client";

export const changePasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/change-password",
  component: ChangePasswordPage,
});

function ChangePasswordPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!user) {
    navigate({ to: "/login" });
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 4) {
      setError("Пароль должен быть не менее 4 символов");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Пароли не совпадают");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await api("/api/change-password", {
        method: "POST",
        body: JSON.stringify({ new_password: newPassword, confirm_password: confirmPassword }),
      });
      navigate({ to: "/main-afl" });
    } catch {
      setError("Ошибка при смене пароля");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[70vh]">
      <div className="card bg-base-100 shadow-xl w-full max-w-md">
        <div className="card-body">
          <h2 className="card-title text-center justify-center mb-2">Смена пароля</h2>
          <p className="text-center text-base-content/50 text-sm mb-4">
            Первый вход — задайте новый пароль
          </p>
          <form onSubmit={handleSubmit}>
            <div className="form-control mb-4">
              <label className="label"><span className="label-text">Новый пароль</span></label>
              <input type="password" className="input input-bordered w-full"
                value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
            </div>
            <div className="form-control mb-6">
              <label className="label"><span className="label-text">Подтверждение</span></label>
              <input type="password" className="input input-bordered w-full"
                value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
            </div>
            {error && <div className="alert alert-error mb-4"><span>{error}</span></div>}
            <button type="submit" className="btn btn-accent w-full" disabled={loading}>
              {loading ? <span className="loading loading-spinner" /> : "Сменить пароль"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
