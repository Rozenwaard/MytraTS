import { createRoute } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { rootRoute } from "../__root";
import { useAuth } from "../../store/auth";
import { useDashboardSummary, useDepartments, useDashboardOverview } from "../../hooks/use-dashboard";

export const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/dashboard",
  component: DashboardPage,
});

function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;

  const [tab, setTab] = useState<"overview" | "errors">("overview");

  return (
    <div className="flex flex-col h-[calc(100vh-68px)] p-3 gap-3">
      <div className="flex-shrink-0 card bg-base-100 shadow-sm rounded-md">
        <div className="flex border-b border-base-200">
          <TabButton active={tab === "overview"} onClick={() => setTab("overview")}>Обзор</TabButton>
          <TabButton active={tab === "errors"} onClick={() => setTab("errors")}>Ошибки</TabButton>
        </div>
      </div>

      {tab === "overview" ? <OverviewTab /> : <ErrorsTab />}
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
        active ? "border-accent text-accent" : "border-transparent text-base-content/60 hover:text-base-content"
      }`}
    >
      {children}
    </button>
  );
}

function OverviewTab() {
  const { data, isLoading } = useDashboardOverview();

  if (isLoading || !data) {
    return (
      <div className="flex items-center justify-center flex-1">
        <span className="loading loading-spinner loading-lg text-accent" />
      </div>
    );
  }

  const cost = data.cost.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div className="flex-1 min-h-0 flex flex-col justify-center">
      <div className="flex flex-wrap gap-3">
        <FullCard label="Заданий" value={data.total.toLocaleString("ru-RU")} />
        <SplitCard
          top={{ label: "ПСК", value: data.psk.toLocaleString("ru-RU") }}
          bottom={{ label: "РЛЭ", value: data.rle.toLocaleString("ru-RU") }}
        />
        <SplitCard
          top={{ label: "План", value: data.plan.toLocaleString("ru-RU") }}
          bottom={{ label: "Внеплан", value: data.unplan.toLocaleString("ru-RU") }}
        />
        <SplitCard
          top={{ label: "Выполнено", value: data.completed.toLocaleString("ru-RU") }}
          bottom={{ label: "Не выполнено", value: data.uncompleted.toLocaleString("ru-RU") }}
        />
        <SplitCard
          top={{ label: "С ошибками", value: data.with_errors.toLocaleString("ru-RU") }}
          bottom={{ label: "Без ошибок", value: data.without_errors.toLocaleString("ru-RU") }}
        />
        <FullCard label="Стоимость" value={`${cost} ₽`} accent="text-accent" />
      </div>
    </div>
  );
}

function FullCard({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="flex-1 min-w-[150px] h-28 card bg-base-100 shadow-sm rounded-md p-4 flex flex-col justify-center">
      <div className="text-xs text-base-content/50">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums truncate ${accent ?? ""}`}>{value}</div>
    </div>
  );
}

function SplitCard({ top, bottom }: { top: { label: string; value: string }; bottom: { label: string; value: string } }) {
  return (
    <div className="flex-1 min-w-[150px] h-28 flex flex-col gap-2">
      <HalfCard label={top.label} value={top.value} />
      <HalfCard label={bottom.label} value={bottom.value} />
    </div>
  );
}

function HalfCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex-1 min-h-0 card bg-base-100 shadow-sm rounded-md px-3 flex flex-col justify-center">
      <div className="text-[11px] text-base-content/50 truncate">{label}</div>
      <div className="text-lg font-semibold tabular-nums truncate leading-tight">{value}</div>
    </div>
  );
}

function ErrorsTab() {
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
        {isAdmin && (
          <>
            <a href={`/api/dashboard/balance-report${qs}`} className="btn btn-outline btn-sm">Балансовая принадлежность</a>
            <a href={`/api/dashboard/date-report${qs}`} className="btn btn-outline btn-sm">Дата работ</a>
            <a href={`/api/dashboard/verified-report${qs}`} className="btn btn-outline btn-sm">Отметка о проверке</a>
          </>
        )}
      </div>

      {isLoading || !data ? (
        <div className="flex items-center justify-center flex-1">
          <span className="loading loading-spinner loading-lg text-accent" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 flex-shrink-0">
            <StatCard label="Заданий в зоне" value={data.total_rows} />
            <StatCard label="С ошибками" value={data.with_errors} accent="text-error" />
            <StatCard label="Отправлено в биллинг" value={data.billed_count} accent="text-success" />
            <StatCard label="На исправлении" value={data.unbilled_count} accent="text-warning" />
            <StatCard label="Всего ошибок" value={data.total_errors} accent="text-error" />
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
