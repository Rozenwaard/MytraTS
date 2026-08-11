import { createRoute } from "@tanstack/react-router";
import { rootRoute } from "../__root";
import { useAuth } from "../../store/auth";

export const mainAflRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/main-afl",
  component: MainAflPage,
});

function MainAflPage() {
  const { user } = useAuth();

  if (!user) {
    return <p>Доступ запрещён</p>;
  }

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Реестры</h1>
      <p className="text-base-content/50">Таблица загружается...</p>
    </div>
  );
}
