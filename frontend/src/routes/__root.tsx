import { createRootRoute, Link, Outlet, useNavigate } from "@tanstack/react-router";
import { useAuth } from "../store/auth";
import { Logo } from "../components/logo";
import { useTheme } from "../lib/use-theme";

export const rootRoute = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <span className="loading loading-spinner loading-lg text-accent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-base-200" data-theme={theme}>
      <nav className="navbar bg-base-100 shadow-lg sticky top-0 z-50 px-4">
        <div className="navbar-start">
          <Link to={user ? "/main-afl" : "/login"} className="text-lg font-bold flex items-center gap-2">
            <Logo />
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
              <button onClick={async () => { await logout(); navigate({ to: "/login" }); }} className="btn btn-ghost btn-sm">
                Выйти
              </button>
              <button onClick={toggle} className="btn btn-sm btn-secondary" title="Переключить тему">
                {theme === "autumn" ? (
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>
                )}
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
