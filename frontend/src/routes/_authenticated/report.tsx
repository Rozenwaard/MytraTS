import { createRoute } from "@tanstack/react-router";
import { useState } from "react";
import { rootRoute } from "../__root";
import { useAuth } from "../../store/auth";
import { useReportCheck } from "../../hooks/use-report-check";

export const reportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/report",
  component: ReportPage,
});

function ReportPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<"check">("check");

  if (!user) return null;

  return (
    <div className="flex flex-col h-[calc(100vh-68px)] p-3 gap-3">
      <div className="flex-shrink-0">
        <div className="card bg-base-100 shadow-sm rounded-md">
          <div className="flex border-b border-base-200">
            {(["check"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px
                  ${tab === t ? "border-accent text-accent" : "border-transparent text-base-content/50 hover:text-base-content/80"}`}
              >
                {t === "check" ? "Проверка" : t}
              </button>
            ))}
          </div>
        </div>
      </div>

      {tab === "check" && <CheckTab />}
    </div>
  );
}

function CheckTab() {
  const { data, isLoading, error } = useReportCheck();
  const [onlyErrors, setOnlyErrors] = useState(true);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <span className="loading loading-spinner loading-lg text-accent" />
      </div>
    );
  }

  if (error || !data) {
    return <div className="alert alert-error"><span>Ошибка загрузки проверки</span></div>;
  }

  const rows = onlyErrors ? data.rows.filter((r) => r.error_count > 0) : data.rows;

  return (
    <div className="space-y-3 min-h-0 flex-1 flex flex-col">
      <div className="grid grid-cols-3 gap-3 flex-shrink-0">
        <StatCard label="Всего проверено" value={data.total} />
        <StatCard label="С ошибками" value={data.with_errors} accent="text-error" />
        <StatCard label="Без ошибок" value={data.total - data.with_errors} accent="text-success" />
      </div>

      <div className="flex items-center gap-3 flex-shrink-0">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" className="toggle toggle-sm" checked={onlyErrors} onChange={(e) => setOnlyErrors(e.target.checked)} />
          <span>Только строки с ошибками</span>
        </label>
        <span className="text-xs text-base-content/50">{rows.length.toLocaleString()} строк</span>
      </div>

      <div className="card bg-base-100 shadow-sm rounded-md overflow-auto flex-1">
        <table className="table table-sm table-zebra">
          <thead className="sticky top-0 bg-base-100 z-10">
            <tr>
              <th>№ задания</th>
              <th>Адрес</th>
              <th>Потребитель</th>
              <th>Вид работы</th>
              <th>Результат</th>
              <th>Исполнитель</th>
              <th>Дата</th>
              <th>Ошибки</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.task_number ?? ""}-${i}`} className={r.error_count > 0 ? "bg-error/5" : undefined}>
                <td className="font-mono text-xs whitespace-nowrap">{r.task_number}</td>
                <td className="text-xs">{r.address}</td>
                <td className="text-xs">{r.subscriber_name}</td>
                <td className="text-xs whitespace-nowrap">{r.work_type}</td>
                <td className="text-xs whitespace-nowrap">{r.work_result}</td>
                <td className="text-xs whitespace-nowrap">{r.executor}</td>
                <td className="text-xs whitespace-nowrap">{r.done_day}</td>
                <td className="text-xs">
                  {r.error_count > 0 ? (
                    <div className="flex flex-col gap-0.5">
                      {r.errors.map((e) => (
                        <span key={e} className="badge badge-error badge-sm justify-start whitespace-nowrap">{e}</span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-success">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <div className="p-6 text-center text-base-content/50 text-sm">Нет данных</div>}
      </div>
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
