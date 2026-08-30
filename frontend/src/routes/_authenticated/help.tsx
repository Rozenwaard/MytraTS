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
  { key: "instruction", label: "Инструкция", accept: ".docx", actions: true },
  { key: "tariffs", label: "Тарифы", accept: ".xlsx", actions: true },
  { key: "operators", label: "Операторы", accept: "", actions: false },
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

        {tabInfo.actions && (
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
        )}
      </div>

      <div className="flex-1 overflow-auto card bg-base-100 shadow-sm rounded-md p-4 scroll-smooth">
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

interface Section {
  id: string;
  title: string;
  blocks: HelpBlock[];
}

function splitBlocks(blocks: HelpBlock[]): { title: string | null; sections: Section[] } {
  const title = blocks[0]?.type === "p" ? (blocks[0].text ?? null) : null;
  const rest = title !== null ? blocks.slice(1) : blocks;
  const sections: Section[] = [];
  let cur: Section | null = null;
  for (const b of rest) {
    if (b.type === "h") {
      cur = { id: `sec-${sections.length}`, title: b.text ?? "", blocks: [] };
      sections.push(cur);
    } else if (cur) {
      cur.blocks.push(b);
    } else {
      sections.push({ id: "sec-0", title: "", blocks: [] });
      cur = sections[0];
      cur.blocks.push(b);
    }
  }
  return { title, sections };
}

function Blocks({ blocks }: { blocks: HelpBlock[] }) {
  if (blocks.length === 0) {
    return <p className="text-base-content/50">Пока пусто</p>;
  }
  const { title, sections } = splitBlocks(blocks);
  const hasMenu = sections.some((s) => s.title !== "");

  return (
    <div className="flex gap-8 items-start">
      <div className="flex-1 min-w-0 max-w-4xl">
        {title && <h1 className="text-2xl font-bold mb-6">{title}</h1>}
        {sections.map((s) => (
          <section key={s.id} id={s.id} className="mb-14 scroll-mt-20">
            {s.title && <h2 className="text-lg font-semibold mb-3 pb-2 border-b border-base-300">{s.title}</h2>}
            {s.blocks.map((b, i) => (
              <Block key={i} b={b} />
            ))}
          </section>
        ))}
      </div>

      {hasMenu && (
        <nav className="w-60 flex-shrink-0 sticky top-16 hidden lg:block">
          <div className="text-xs font-semibold text-base-content/50 uppercase tracking-wide mb-2">Разделы</div>
          <ul className="space-y-0.5">
            {sections.filter((s) => s.title).map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="block text-sm text-base-content/70 hover:text-accent py-1.5 border-l-2 border-transparent hover:border-accent pl-2">
                  {s.title}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </div>
  );
}

function Block({ b }: { b: HelpBlock }) {
  if (b.type === "p") {
    return <p className="whitespace-pre-line leading-relaxed text-sm text-base-content/85 mb-2">{b.text}</p>;
  }
  if (b.type === "table") {
    return <TableBlock rows={b.rows ?? []} />;
  }
  return null;
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
