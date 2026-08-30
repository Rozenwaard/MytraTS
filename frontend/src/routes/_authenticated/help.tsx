import { createRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { rootRoute } from "../__root";
import { useAuth } from "../../store/auth";
import { fetchHelpPage, uploadHelpPage, type HelpBlock, type HelpPageData } from "../../api/help";

export const helpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/help",
  component: HelpPage,
});

const TABS = [
  { key: "instruction", label: "Инструкция", accept: ".docx" },
  { key: "tariffs", label: "Тарифы", accept: ".xlsx" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function HelpPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<TabKey>("instruction");
  const [data, setData] = useState<HelpPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  };

  const load = async (key: TabKey) => {
    setLoading(true);
    try {
      setData(await fetchHelpPage(key));
    } catch {
      showToast("Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(tab);
  }, [tab]);

  const tabInfo = TABS.find((t) => t.key === tab)!;

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    try {
      await uploadHelpPage(tab, file);
      showToast("Обновлено");
      await load(tab);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-68px)] p-3 gap-3">
      <div className="flex-shrink-0 card bg-base-100 shadow-sm rounded-md">
        <div className="flex border-b border-base-200">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
                tab === t.key ? "border-accent text-accent" : "border-transparent text-base-content/60 hover:text-base-content"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2 px-3 py-2">
          {user?.role === "администратор" && (
            <>
              <button className="btn btn-accent btn-sm" onClick={() => fileInput.current?.click()} disabled={uploading}>
                {uploading ? "Загружаем…" : "Обновить"}
              </button>
              <input
                ref={fileInput}
                type="file"
                accept={tabInfo.accept}
                className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0])}
              />
            </>
          )}
          <a href={`/api/help/${tab}/download`} className="btn btn-outline btn-sm">
            Скачать
          </a>
          {data?.updated_at && <span className="text-xs text-base-content/50 ml-auto">Обновлено: {data.updated_at}</span>}
        </div>
      </div>

      <div className="flex-1 overflow-auto card bg-base-100 shadow-sm rounded-md p-4">
        {loading ? (
          <div className="flex justify-center py-12"><span className="loading loading-spinner loading-lg text-accent" /></div>
        ) : (
          <Blocks blocks={data?.blocks ?? []} />
        )}
      </div>

      {toast && (
        <div className="toast toast-top toast-center z-50">
          <div className="alert alert-success">{toast}</div>
        </div>
      )}
    </div>
  );
}

function Blocks({ blocks }: { blocks: HelpBlock[] }) {
  if (blocks.length === 0) {
    return <p className="text-base-content/50">Пока пусто</p>;
  }
  return (
    <div className="max-w-4xl">
      {blocks.map((b, i) =>
        b.type === "p" ? (
          <p
            key={i}
            className={`whitespace-pre-line leading-relaxed ${
              i === 0 ? "text-xl font-semibold mb-3" : "text-sm text-base-content/80 mb-2"
            }`}
          >
            {b.text}
          </p>
        ) : (
          <TableBlock key={i} rows={b.rows ?? []} />
        )
      )}
    </div>
  );
}

function TableBlock({ rows }: { rows: string[][] }) {
  if (rows.length === 0) return null;
  const header = rows[0];
  const body = rows.slice(1);
  return (
    <div className="overflow-x-auto my-3">
      <table className="table table-sm table-zebra table-pin-rows border border-base-300">
        <thead>
          <tr>
            {header.map((h, i) => (
              <th key={i} className="whitespace-pre-line text-left">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, ri) => (
            <tr key={ri}>
              {row.map((c, ci) => (
                <td key={ci} className="whitespace-pre-line align-top">{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
