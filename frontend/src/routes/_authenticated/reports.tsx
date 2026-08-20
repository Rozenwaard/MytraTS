import { createRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { rootRoute } from "../__root";
import { useAuth } from "../../store/auth";
import { fetchFinReport, addToReport, type FinReportData, type FinCardData } from "../../api/fin-report";

export const reportsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reports",
  component: ReportsPage,
});

const MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"];

function monthOptions(): { value: string; label: string }[] {
  const now = new Date();
  const opts: { value: string; label: string }[] = [];
  for (let i = 1; i <= 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    opts.push({
      value: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
      label: MONTHS[d.getMonth()],
    });
  }
  return opts;
}

function periodLabel(period: string): string {
  const [year, month] = period.split("-");
  return `Отчёт за ${MONTHS[Number(month) - 1]} ${year}`;
}

function ReportsPage() {
  const { user } = useAuth();
  if (!user || user.role !== "администратор") {
    return <div className="p-6 text-base-content/60">Нет доступа</div>;
  }

  const [tab, setTab] = useState<"fin">("fin");

  return (
    <div className="flex flex-col h-[calc(100vh-68px)] p-3 gap-3">
      <div className="flex-shrink-0 card bg-base-100 shadow-sm rounded-md">
        <div className="flex border-b border-base-200">
          <button
            onClick={() => setTab("fin")}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === "fin" ? "border-accent text-accent" : "border-transparent text-base-content/60 hover:text-base-content"
            }`}
          >
            Финотчёт
          </button>
        </div>
      </div>

      {tab === "fin" && <FinReportTab />}
    </div>
  );
}

function FinReportTab() {
  const [options] = useState(monthOptions);
  const [period, setPeriod] = useState(options[0].value);
  const [data, setData] = useState<FinReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  };

  const load = async (p: string) => {
    setLoading(true);
    try {
      setData(await fetchFinReport(p));
    } catch {
      showToast("Ошибка загрузки финотчёта");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(period);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  const toggleExpand = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleAdd = async () => {
    try {
      const res = await addToReport(period);
      showToast(`Добавлено в отчёт: ${res.updated}`);
      await load(period);
    } catch {
      showToast("Ошибка добавления в отчёт");
    }
  };

  const handleDownload = () => {
    showToast("Скачивание отчёта — в разработке");
  };

  const cards: { key: keyof FinReportData["cards"]; label: string }[] = [
    { key: "completed", label: "Заданий завершено" },
    { key: "without_reestr", label: "Исполнено без реестров" },
    { key: "with_errors", label: "Заданий с ошибками" },
    { key: "ready", label: "Готово к отчёту" },
  ];

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-3">
      <div className="flex-shrink-0 flex flex-wrap items-center gap-2">
        <select className="select select-bordered select-sm" value={period} onChange={(e) => setPeriod(e.target.value)}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <button className="btn btn-accent btn-sm" onClick={handleAdd}>Добавить в отчёт</button>
        <button className="btn btn-outline btn-sm" onClick={handleDownload}>Скачать отчёт</button>
      </div>

      <div className="flex-1 min-h-0 flex gap-6">
        <div className="flex-1 min-w-0">
          {loading || !data ? (
            <div className="flex items-center justify-center h-full">
              <span className="loading loading-spinner loading-lg text-accent" />
            </div>
          ) : (
            <div className="flex flex-wrap gap-3 items-start">
              {cards.map((c) => (
                <FinCard
                  key={c.key}
                  label={c.label}
                  card={data.cards[c.key]}
                  expanded={expanded.has(c.key)}
                  onToggle={() => toggleExpand(c.key)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="w-[330px] flex-shrink-0 card bg-base-100 shadow-sm rounded-md p-4 self-start">
          <div className="text-xs text-base-content/50 mb-2 font-medium">{periodLabel(period)}</div>
          {loading || !data ? (
            <span className="loading loading-spinner loading-sm text-accent" />
          ) : data.work_types.length === 0 ? (
            <div className="text-sm text-base-content/50">Нет данных за период</div>
          ) : (
            <div className="space-y-1">
              {data.work_types.map((w) => (
                <div key={w.label} className="flex justify-between gap-2 text-sm">
                  <span className="text-base-content/70">{w.label}</span>
                  <span className="font-semibold tabular-nums">{w.count.toLocaleString("ru-RU")}</span>
                </div>
              ))}
            </div>
          )}
          <div className="border-t border-base-300 mt-3 pt-2 flex justify-between text-sm font-semibold">
            <span>Итого</span>
            <span className="tabular-nums">
              {data ? data.total_cost.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "0,00"} ₽
            </span>
          </div>
        </div>
      </div>

      {toast && (
        <div className="toast toast-top toast-center z-50">
          <div className="alert alert-info">{toast}</div>
        </div>
      )}
    </div>
  );
}

function FinCard({ label, card, expanded, onToggle }: { label: string; card: FinCardData; expanded: boolean; onToggle: () => void }) {
  return (
    <div className="card bg-base-100 shadow-sm rounded-md min-w-[170px]">
      <button className="w-full text-left p-4" onClick={onToggle}>
        <div className="text-xs text-base-content/50">{label}</div>
        <div className="text-2xl font-semibold tabular-nums flex items-center gap-1">
          {card.total.toLocaleString("ru-RU")}
          <span className="text-xs text-base-content/40">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>
      {expanded && (
        <div className="px-4 pb-3 space-y-1">
          {card.by_locale.length === 0 ? (
            <div className="text-xs text-base-content/50">Нет данных</div>
          ) : (
            card.by_locale.map((b) => (
              <div key={b.locale} className="flex justify-between gap-4 text-sm">
                <span className="text-base-content/70">{b.locale}</span>
                <span className="font-semibold tabular-nums">{b.count.toLocaleString("ru-RU")}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

