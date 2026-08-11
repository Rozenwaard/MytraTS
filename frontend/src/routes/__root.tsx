import { createRootRoute, Link, Outlet } from "@tanstack/react-router";
import { useAuth } from "../store/auth";

export const rootRoute = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  const { user, loading, logout } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <span className="loading loading-spinner loading-lg text-accent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-base-200" data-theme="autumn">
      <nav className="navbar bg-base-100 shadow-lg sticky top-0 z-50 px-4">
        <div className="navbar-start">
          <Link to={user ? "/main-afl" : "/login"} className="text-lg font-bold flex items-center gap-2">
            <span className="w-8 h-8 bg-accent rounded-lg flex items-center justify-center text-base-100 text-sm">⚡</span>
            <span className="text-accent">MYTRA</span>
          </Link>
        </div>

        {user && (
          <div className="navbar-center flex gap-1">
            <Link to="/main-afl" className="btn btn-ghost btn-sm" activeProps={{ className: "btn-active" }}>
              Реестры
            </Link>
            <Link to="/main-afl" className="btn btn-ghost btn-sm">
              Архив
            </Link>
          </div>
        )}

        <div className="navbar-end flex items-center gap-2">
          {user ? (
            <>
              <span className="text-sm text-base-content/70 hidden sm:inline">{user.full_name}</span>
              <button onClick={logout} className="btn btn-ghost btn-sm">
                Выйти
              </button>
            </>
          ) : (
            <Link to="/login" className="btn btn-ghost btn-sm">
              Войти
            </Link>
          )}
        </div>
      </nav>

      <main>
        <Outlet />
      </main>
    </div>
  );
}
