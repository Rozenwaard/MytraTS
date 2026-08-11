import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type SortingState,
  getSortedRowModel,
} from "@tanstack/react-table";
import { useState } from "react";

interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  total: number;
  page: number;
  perPage: number;
  selectedIds: Set<string>;
  onRowClick: (id: string) => void;
  onSort: (sort: string, order: string) => void;
  onPage: (page: number) => void;
  getId: (row: TData) => string;
}

export function DataTable<TData>({
  columns,
  data,
  total,
  page,
  perPage,
  selectedIds,
  onRowClick,
  onSort,
  onPage,
  getId,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: (updater) => {
      const next = typeof updater === "function" ? updater(sorting) : updater;
      setSorting(next);
      if (next.length > 0) onSort(next[0].id, next[0].desc ? "desc" : "asc");
    },
    getSortedRowModel: getSortedRowModel(),
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
  });

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="card bg-base-100 shadow-sm flex flex-col h-full rounded-md">
      <div className="overflow-x-auto flex-1">
        <table className="table table-sm table-zebra table-pin-rows">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    className="cursor-pointer select-none whitespace-nowrap text-center"
                    onClick={h.column.getToggleSortingHandler()}
                  >
                    <span className="inline-flex items-center gap-1">
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {{ asc: " ▲", desc: " ▼" }[h.column.getIsSorted() as string] ?? ""}
                    </span>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => {
              const id = getId(row.original);
              return (
                <tr
                  key={id}
                  className={`cursor-pointer ${selectedIds.has(id) ? "bg-accent/15 hover:bg-accent/20" : "hover:bg-base-200"}`}
                  onClick={() => onRowClick(id)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="whitespace-nowrap text-sm">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between px-3 py-2 border-t border-base-300 flex-shrink-0">
        <span className="text-sm text-base-content/60">Всего: {total}</span>
        <div className="join">
          <button className="join-item btn btn-xs" disabled={page <= 1} onClick={() => onPage(page - 1)}>«</button>
          {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
            const p = i + Math.max(1, page - 3);
            return p <= totalPages ? (
              <button key={p} className={`join-item btn btn-xs ${p === page ? "btn-active" : ""}`} onClick={() => onPage(p)}>{p}</button>
            ) : null;
          })}
          <button className="join-item btn btn-xs" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>»</button>
        </div>
      </div>
    </div>
  );
}
