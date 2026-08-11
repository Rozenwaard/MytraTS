import { createRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { rootRoute } from "../__root";
import { useAuth } from "../../store/auth";
import { useMainAfl, useMainAflStats } from "../../hooks/use-main-afl";
import { DataTable } from "../../components/table/data-table";
import type { MainAflRow, MainAflParams } from "../../api/main-afl";
import { createReestr, resetReestr, fetchReestrList, downloadReestrUrl } from "../../api/main-afl";

export const mainAflRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/main-afl",
  component: MainAflPage,
});

const columns: ColumnDef<MainAflRow>[] = [
  { accessorKey: "task_number", header: "№ задания" },
  { accessorKey: "task_source", header: "Источник" },
  { accessorKey: "task_type", header: "Вид задания" },
  { accessorKey: "work_type_in_task", header: "Поручение" },
  { accessorKey: "personal_account", header: "Точка учёта" },
  { accessorKey: "subscriber_name", header: "Потребитель" },
  { accessorKey: "address", header: "Адрес" },
  { accessorKey: "municipal_district", header: "Район" },
  { accessorKey: "house_type", header: "Тип дома" },
  { accessorKey: "service_object_type", header: "Объект" },
  { accessorKey: "meter_installation_place", header: "Место ПУ" },
  { accessorKey: "meter_status", header: "Статус" },
  { accessorKey: "meter_ownership", header: "Принадлежность" },
  { accessorKey: "violations", header: "Нарушения" },
  { accessorKey: "comment", header: "Комментарий" },
  { accessorKey: "customer", header: "Заказчик" },
  { accessorKey: "executor", header: "Исполнитель" },
  { accessorKey: "visit_reason", header: "Основание" },
  { accessorKey: "task_output", header: "Результат" },
  { accessorKey: "task_report", header: "Отчёт" },
  { accessorKey: "grid", header: "Сеть" },
  { accessorKey: "done_day", header: "Дата" },
  { accessorKey: "reestr_number", header: "Реестр" },
];


function MainAflPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<"add" | "list" | "settings">("add");
  const [params, setParams] = useState<MainAflParams>({ page: 1, per_page: 50 });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);
  const [reestrs, setReestrs] = useState<string[]>([]);
  const [reestrMeta, setReestrMeta] = useState<Record<string, { task_report: string | null; customer: string | null }>>({});
  const [activeReestr, setActiveReestr] = useState<string>("");
  const [emptyReestrs, setEmptyReestrs] = useState<Set<string>>(new Set());
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data, isLoading, refetch } = useMainAfl(params);
  const rows = data?.rows ?? [];
  const total = data?.total ?? 0;

  const getId = useCallback((row: MainAflRow) => row.task_number ?? "", []);

  const toggleRow = useCallback((id: string) => {
    setSelected((prev) => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });
  }, []);

  const showToast = (msg: string) => {
    setToast(msg);
    if (toastTimer.current !== null) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  };

  const loadReestrs = async () => {
    const data = await fetchReestrList();
    setReestrs(data.reestrs);
    setReestrMeta(data.meta);
    if (data.reestrs.length > 0 && !activeReestr) {
      setActiveReestr(data.reestrs[0]);
    }
  };

  useEffect(() => { loadReestrs(); }, []);

  const handleCreateReestr = async () => {
    if (selected.size === 0) { showToast("Не выбраны строки"); return; }
    try {
      const result = await createReestr([...selected]);
      const parts = result.reestrs.map((r) =>
        r.reestr_number === "Отклонён" ? `${r.task_report}: отклонён` : `${r.reestr_number} — ${r.task_report} (${r.count})`
      );
      showToast(parts.join(" | ") || "Готово");
      setSelected(new Set()); refetch(); loadReestrs();
    } catch { showToast("Ошибка создания реестра"); }
  };

  const handleResetReestr = async () => {
    if (selected.size === 0) { showToast("Не выбраны строки"); return; }
    try {
      const result = await resetReestr([...selected]);
      showToast(`Сброшено: ${result.cleared}`);
      setSelected(new Set()); refetch(); loadReestrs();
    } catch { showToast("Ошибка сброса реестра"); }
  };

  const handleResetFilters = () => { setParams({ page: 1, per_page: 50 }); setSelected(new Set()); };

  const handleSelectReestr = (rn: string) => {
    setParams({ ...params, reestr: rn, page: 1 });
  };

  const toggleEmpty = (rn: string) => {
    setEmptyReestrs((prev) => { const next = new Set(prev); next.has(rn) ? next.delete(rn) : next.add(rn); return next; });
  };

  if (!user) return null;

  return (
    <div className="flex flex-col h-[calc(100vh-68px)] p-3 gap-3">
      {toast && <div className="fixed top-16 right-4 z-50 alert alert-success shadow-lg w-auto max-w-lg py-2 px-4 text-sm"><span>{toast}</span></div>}

      <div className="flex-shrink-0">
        <div className="card bg-base-100 shadow-sm rounded-md">
          <div className="flex border-b border-base-200">
            {(["add", "list", "settings"] as const).map((t) => (
              <button key={t} onClick={() => {
                setTab(t);
                if (t === "list") { loadReestrs(); setParams({ page: 1, per_page: 50, reestr: activeReestr || reestrs[0] || undefined }); }
                if (t === "add") { setParams({ page: 1, per_page: 50, reestr: undefined }); }
              }}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px
                  ${tab === t ? "border-accent text-accent" : "border-transparent text-base-content/50 hover:text-base-content"}`}>
                {{ add: "Добавление", list: "Список", settings: "Настройка" }[t]}
              </button>
            ))}
          </div>

          <div className="py-2 px-3">
            {tab === "add" && <AddTab params={params} setParams={setParams} onReset={handleResetFilters} onCreate={handleCreateReestr} />}
            {tab === "list" && <ListTab reestrs={reestrs} activeReestr={activeReestr} setActiveReestr={setActiveReestr} emptyReestrs={emptyReestrs} toggleEmpty={toggleEmpty} onReset={handleResetReestr} onSelectReestr={handleSelectReestr} meta={reestrMeta} />}
            {tab === "settings" && <SettingsTab />}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {isLoading ? (
          <div className="flex justify-center py-12"><span className="loading loading-spinner loading-lg text-accent" /></div>
        ) : (
          <DataTable columns={columns} data={rows} total={total}
            page={params.page ?? 1} perPage={params.per_page ?? 50}
            selectedIds={selected} onRowClick={toggleRow}
            onSort={(sort, order) => setParams({ ...params, sort, order })}
            onPage={(page) => setParams({ ...params, page })}
            getId={getId} />
        )}
      </div>
    </div>
  );

function AddTab({ params, setParams, onReset, onCreate }: {
  params: MainAflParams; setParams: (p: MainAflParams) => void;
  onReset: () => void; onCreate: () => void;
}) {
  const { data: stats } = useMainAflStats();

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2 items-center">
        <input type="text" placeholder="Поиск по адресу, № задания или л/с" className="input input-bordered input-sm flex-1 min-w-[220px]"
          value={params.search ?? ""} onChange={(e) => setParams({ ...params, search: e.target.value || undefined, page: 1 })} />
        <input type="text" placeholder="Дата работ" className="input input-bordered input-sm w-[140px]"
          value={(params as Record<string, string>).done_day ?? ""} onChange={(e) => setParams({ ...params, done_day: e.target.value || undefined } as MainAflParams)} />
        <button className="btn btn-ghost btn-sm" onClick={onReset}>Сброс фильтров</button>
        <button className="btn btn-accent btn-sm" onClick={onCreate}>В реестр</button>
      </div>
      <div className="border-t border-base-200" />
      <div className="grid grid-cols-3 gap-6 text-sm">
        <div>
          <div className="text-xs text-base-content/40 mb-1.5 font-medium">Статистика</div>
          <div className="flex flex-col gap-y-0.5 text-xs">
            {[
              { label: "ПСК", count: stats?.customers?.["ПСК"] },
              { label: "РЛЭ", count: stats?.customers?.["РЛЭ"] },
              { label: "План", count: stats?.plan },
              { label: "Внеплан", count: stats?.unplan },
              { label: "Выполнено", count: stats?.completed },
              { label: "Не выполнено", count: stats?.uncompleted },
              { label: "С реестром", count: stats?.with_reestr },
              { label: "Без реестра", count: stats?.without_reestr },
            ].map((s) => (
              <button key={s.label} className="text-left cursor-pointer hover:underline flex gap-1"
                onClick={() => {
                  if (s.label === "ПСК") setParams({ ...params, customer: params.customer === "ПСК" ? undefined : "ПСК", page: 1 });
                  if (s.label === "РЛЭ") setParams({ ...params, customer: params.customer === "РЛЭ" ? undefined : "РЛЭ", page: 1 });
                  if (s.label === "План") setParams({ ...params, task_type: params.task_type === "Плановый" ? undefined : "Плановый", page: 1 } as MainAflParams);
                  if (s.label === "Внеплан") setParams({ ...params, task_type: params.task_type === "Внеплановый" ? undefined : "Внеплановый", page: 1 } as MainAflParams);
                  if (s.label === "Выполнено") setParams({ ...params, only_completed: params.only_completed ? undefined : true, page: 1 });
                  if (s.label === "Не выполнено") setParams({ ...params, only_completed: undefined, page: 1 } as MainAflParams);
                  if (s.label === "С реестром") setParams({ ...params, only_without_reestr: undefined, page: 1 });
                  if (s.label === "Без реестра") setParams({ ...params, only_without_reestr: params.only_without_reestr ? undefined : true, page: 1 });
                }}>
                <span className="text-base-content/70">{s.label}</span>
                <span className="font-semibold tabular-nums ml-auto">{s.count != null ? s.count.toLocaleString() : "—"}</span>
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="text-xs text-base-content/40 mb-1.5 font-medium">По видам работ</div>
          <div className="flex flex-col gap-y-0.5 text-xs">
            {stats?.task_reports?.map((tr) => (
              <button key={tr.label} className="text-left cursor-pointer hover:underline flex gap-1"
                onClick={() => setParams({ ...params, task_report: params.task_report === (tr.label === "Не выполнено" ? undefined : tr.label) ? undefined : (tr.label === "Не выполнено" ? "" : tr.label), page: 1 } as MainAflParams)}>
                <span className="text-base-content/70">{tr.label}</span>
                <span className="font-semibold tabular-nums ml-auto">{tr.count.toLocaleString()}</span>
              </button>
            )) ?? <span className="text-base-content/50">—</span>}
          </div>
        </div>
        <div>
          <div className="text-xs text-base-content/40 mb-1.5 font-medium">По исполнителям</div>
          <div className="flex flex-col gap-y-0.5 text-xs">
            {stats?.executors?.map((ex) => (
              <button key={ex.label} className="text-left cursor-pointer hover:underline flex gap-1.5"
                onClick={() => setParams({ ...params, executor_filter: params.executor_filter === ex.label ? undefined : ex.label, page: 1 })}>
                <span className="text-base-content/70 truncate">{ex.label}</span>
                <span className="font-semibold tabular-nums ml-auto">{ex.count.toLocaleString()}</span>
              </button>
            )) ?? <span className="text-base-content/50">—</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function ListTab({ reestrs, activeReestr, setActiveReestr, emptyReestrs, toggleEmpty, onReset, onSelectReestr, meta }: {
  reestrs: string[]; activeReestr: string; setActiveReestr: (r: string) => void;
  emptyReestrs: Set<string>; toggleEmpty: (rn: string) => void; onReset: () => void;
  onSelectReestr: (rn: string) => void;
  meta: Record<string, { task_report: string | null; customer: string | null }>;
}) {
  const m = meta[activeReestr];
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2 items-center">
        {reestrs.map((rn) => (
          <button key={rn} onClick={() => { setActiveReestr(rn); onSelectReestr(rn); }}
            className={`text-sm px-2 py-0.5 rounded ${activeReestr === rn ? "bg-accent text-accent-content" : "bg-base-200 hover:bg-base-300"}`}>
            {rn}{emptyReestrs.has(rn) ? " (П)" : ""}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-3 items-center">
        <button className="btn btn-ghost btn-xs" onClick={() => activeReestr && window.open(downloadReestrUrl(activeReestr), "_blank")}>Печать</button>
        <button className="btn btn-ghost btn-xs" onClick={() => activeReestr && toggleEmpty(activeReestr)}>
          {activeReestr && emptyReestrs.has(activeReestr) ? "Снять (П)" : "Пустой"}
        </button>
        <button className="btn btn-ghost btn-xs" onClick={onReset}>Удалить из реестра</button>
        {m && (
          <>
            <span className="text-xs text-base-content/40">|</span>
            <span className="text-xs text-base-content/50">Вид работ: <span className="text-base-content">{m.task_report ?? "—"}</span></span>
            <span className="text-xs text-base-content/50">Заказчик: <span className="text-base-content">{m.customer ?? "—"}</span></span>
          </>
        )}
      </div>
    </div>
  );
}

}

function SettingsTab() {
  const [cols, setCols] = useState(() => columns.map((c, i) => ({ key: (c as { accessorKey?: string }).accessorKey ?? "", label: (typeof c.header === "string" ? c.header : "") as string, visible: true, order: i })));
  const dragItem = useRef<number | null>(null);
  const dragOver = useRef<number | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    fetch("/api/user/settings", { credentials: "include" })
      .then((r) => r.json())
      .then((data) => {
        if (data.settings?.columns) {
          const savedCols = data.settings.columns as { key: string; visible: boolean; order: number }[];
          const merged = columns.map((c, i) => {
            const sc = savedCols.find((sc) => sc.key === (c as { accessorKey?: string }).accessorKey);
            return { key: (c as { accessorKey?: string }).accessorKey ?? "", label: (typeof c.header === "string" ? c.header : "") as string, visible: sc?.visible ?? true, order: sc?.order ?? i };
          });
          merged.sort((a, b) => a.order - b.order);
          setCols(merged);
        }
      }).catch(() => {});
  }, []);

  const save = (updated: typeof cols) => {
    if (saveTimer.current !== null) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      fetch("/api/user/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ settings: { columns: updated.map((c) => ({ key: c.key, visible: c.visible, order: c.order })) } }),
      });
    }, 500);
  };

  const toggle = (key: string) => {
    setCols((prev) => { const next = prev.map((c) => (c.key === key ? { ...c, visible: !c.visible } : c)); save(next); return next; });
  };

  const handleDragStart = (idx: number) => { dragItem.current = idx; };
  const handleDragOver = (e: React.DragEvent, idx: number) => { e.preventDefault(); dragOver.current = idx; };
  const handleDrop = () => {
    if (dragItem.current === null || dragOver.current === null) return;
    const newCols = [...cols];
    const visOnly = newCols.filter((c) => c.visible).sort((a, b) => a.order - b.order);
    const [moved] = visOnly.splice(dragItem.current, 1);
    visOnly.splice(dragOver.current, 0, moved);
    const reordered = cols.map((c) => {
      const vi = visOnly.findIndex((v) => v.key === c.key);
      return vi >= 0 ? { ...c, order: vi } : c;
    });
    setCols(reordered);
    save(reordered);
    dragItem.current = null;
    dragOver.current = null;
  };

  const visible = cols.filter((c) => c.visible).sort((a, b) => a.order - b.order);

  return (
    <div className="space-y-2 text-sm">
      <div className="text-xs text-base-content/40 font-medium">Порядок и видимость колонок (перетащите)</div>
      <div className="flex flex-wrap gap-1.5">
        {visible.map((c, i) => (
          <div key={c.key} draggable className="flex items-center gap-1.5 px-2 py-1 bg-base-200 rounded cursor-grab active:cursor-grabbing text-xs"
            onDragStart={() => handleDragStart(i)} onDragOver={(e) => handleDragOver(e, i)} onDrop={handleDrop}>
            <span className="text-base-content/30">⠿</span>
            <input type="checkbox" className="checkbox checkbox-xs" checked={true} onChange={() => toggle(c.key)} />
            <span>{c.label}</span>
          </div>
        ))}
      </div>
      {cols.some((c) => !c.visible) && (
        <div className="flex flex-wrap gap-1">
          {cols.filter((c) => !c.visible).map((c) => (
            <button key={c.key} className="btn btn-ghost btn-xs text-xs" onClick={() => toggle(c.key)}>
              + {c.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

