import { createRoute } from "@tanstack/react-router";
import { useCallback, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { rootRoute } from "../__root";
import { useAuth } from "../../store/auth";
import { useMainAfl } from "../../hooks/use-main-afl";
import { DataTable } from "../../components/table/data-table";
import type { MainAflRow, MainAflParams } from "../../api/main-afl";

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
  { accessorKey: "personal_account", header: "Л/с" },
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
  const [params, setParams] = useState<MainAflParams>({ page: 1, per_page: 50 });
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data, isLoading } = useMainAfl(params);
  const rows = data?.rows ?? [];
  const total = data?.total ?? 0;

  const getId = useCallback((row: MainAflRow) => row.task_number ?? "", []);

  const toggleRow = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    setSelected((prev) =>
      prev.size === rows.length ? new Set() : new Set(rows.map(getId))
    );
  }, [rows, getId]);

  if (!user) return <p className="p-4">Доступ запрещён</p>;

  return (
    <div className="flex flex-col h-[calc(100vh-68px)] p-3 gap-3">
      <div className="card bg-base-100 shadow-sm flex-shrink-0">
        <div className="card-body py-2 px-3">
          <div className="flex flex-wrap gap-2 items-center">
            <input
              type="text"
              placeholder="Поиск по адресу, № задания или л/с"
              className="input input-bordered input-sm flex-1 min-w-[200px]"
              value={params.search ?? ""}
              onChange={(e) => setParams({ ...params, search: e.target.value || undefined, page: 1 })}
            />
            <select
              className="select select-bordered select-sm"
              value={params.customer ?? ""}
              onChange={(e) => setParams({ ...params, customer: e.target.value || undefined, page: 1 })}
            >
              <option value="">Заказчики</option>
              <option value="ПСК">ПСК</option>
              <option value="РЛЭ">РЛЭ</option>
            </select>
            <label className="label cursor-pointer gap-1 px-1">
              <input type="checkbox" className="checkbox checkbox-sm checkbox-accent"
                checked={params.only_completed ?? false}
                onChange={(e) => setParams({ ...params, only_completed: e.target.checked || undefined, page: 1 })} />
              <span className="label-text text-xs">Выполненные</span>
            </label>
            <label className="label cursor-pointer gap-1 px-1">
              <input type="checkbox" className="checkbox checkbox-sm checkbox-accent"
                checked={params.only_without_reestr ?? false}
                onChange={(e) => setParams({ ...params, only_without_reestr: e.target.checked || undefined, page: 1 })} />
              <span className="label-text text-xs">Без реестра</span>
            </label>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <span className="loading loading-spinner loading-lg text-accent" />
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-hidden">
          <DataTable
            columns={columns} data={rows} total={total}
            page={params.page ?? 1} perPage={params.per_page ?? 50}
            selectedRows={selected} onSelectRow={toggleRow} onSelectAll={toggleAll}
            onSort={(sort, order) => setParams({ ...params, sort, order })}
            onPage={(page) => setParams({ ...params, page })}
            getId={getId}
          />
        </div>
      )}
    </div>
  );
}
