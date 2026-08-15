import { createRoute } from "@tanstack/react-router";
import { useState } from "react";
import { rootRoute } from "../__root";
import { useAuth } from "../../store/auth";
import { useDashboardSummary, useDepartments } from "../../hooks/use-dashboard";

export const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/dashboard",
  component: DashboardPage,
});

function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <div className="flex flex-col h-[calc(100vh-68px)] p-3 gap-3">
      <div className="flex-shrink-0 card bg-base-100 shadow-sm rounded-md">
        <div className="flex border-b border-base-200">
          <button className="px-4 py-2 text-sm font-medium border-b-2 border-accent text-accent -mb-px">Обзор</button>
        </div>
      </div>

      <OverviewTab />
    </div>
  );
}

function OverviewTab() {
  const { user } = useAuth();
  const isAdmin = user?.role === "администратор" || user?.role === "специалист";
  const [dept, setDept] = useState("");
  const { data: depts } = useDepartments(isAdmin);
  const { data, isLoading } = useDashboardSummary(dept);

  const qs = dept ? `?dept=${encodeURIComponent(dept)}` : "";

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-3">
      <div className="flex-shrink-0 flex flex-wrap items-center gap-2">
        {isAdmin && (
          <select className="select select-bordered select-sm" value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="">Все отделения</option>
            {(depts ?? []).map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        )}
        <a href={`/api/dashboard/errors-report${qs}`} className="btn btn-accent btn-sm">Отчёт об ошибках</a>
        <a href={`/api/dashboard/balance-report${qs}`} className="btn btn-outline btn-sm">Балансовая принадлежность</a>
      </div>

      {isLoading || !data ? (
        <div className="flex items-center justify-center flex-1">
          <span className="loading loading-spinner loading-lg text-accent" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 flex-shrink-0">
            <StatCard label="Заданий с ошибками" value={data.total_with_errors} accent="text-error" />
            <StatCard label="Всего ошибок" value={data.total_errors} accent="text-accent" />
          </div>

          {data.errors.length === 0 ? (
            <div className="text-center text-base-content/50 text-sm py-10">Нет ошибок в зоне стоп-фактора</div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 content-start">
              {data.errors.map((e) => (
                <div key={e.label} className="card bg-base-100 shadow-sm rounded-md px-3 py-2">
                  <div className="text-lg font-semibold tabular-nums leading-none">{e.count}</div>
                  <div className="text-[11px] text-base-content/60 leading-tight mt-1">{e.label}</div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div className="card bg-base-100 shadow-sm rounded-md p-4">
      <div className="text-xs text-base-content/50">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums ${accent ?? ""}`}>{value.toLocaleString()}</div>
    </div>
  );
}
