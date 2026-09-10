"""Разбор и подготовка справочных страниц «Помощь»: Инструкция (.docx), Тарифы (.xlsx).

Контент хранится в виде JSON-блоков: [{type:"p",text}, {type:"table",rows:[[...],...]}].
"""

import html
import io
import re
import zipfile

from openpyxl import load_workbook
from python_calamine import CalamineWorkbook


HELP_KEYS = {
    "instruction": "Инструкция",
    "tariffs": "Тарифы",
    "operators": "Операторы",
    "task-report": "Отчёт по заданию",
}


def _unescape(text: str) -> str:
    return html.unescape(text).strip()


def _paragraph_text(p_xml: str) -> str:
    p_xml = re.sub(r"<w:br[^>]*/>", "\n", p_xml)
    texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", p_xml, re.S)
    joined = "".join(re.sub(r"<[^>]+>", "", t) for t in texts)  # убрать «протёкшие» xml-теги
    joined = re.sub(r"(?<=\S)–", " –", joined)                   # пробел перед тире после кода
    return _unescape(joined)


def _cell_text(tc_xml: str) -> str:
    paras = re.findall(r"<w:p[ >].*?</w:p>", tc_xml, re.S)
    if not paras:
        paras = [tc_xml]
    lines = [_paragraph_text(p) for p in paras]
    return "\n".join(line for line in lines if line)


def _table_rows(tbl_xml: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in re.findall(r"<w:tr[ >].*?</w:tr>", tbl_xml, re.S):
        cells = [_cell_text(tc) for tc in re.findall(r"<w:tc[ >].*?</w:tc>", tr, re.S)]
        rows.append(cells)
    return rows


def parse_docx_to_blocks(content: bytes) -> list[dict]:
    """docx → упорядоченные блоки (абзацы и таблицы), слово в слово."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")

    blocks: list[dict] = []
    for m in re.finditer(r"<w:p[ >].*?</w:p>|<w:tbl[ >].*?</w:tbl>", xml, re.S):
        chunk = m.group(0)
        if chunk.startswith("<w:p"):
            text = _paragraph_text(chunk)
            if text:
                blocks.append({"type": "p", "text": text})
        else:
            rows = _table_rows(chunk)
            if rows:
                blocks.append({"type": "table", "rows": rows})
    return blocks


def _postprocess_instruction(blocks: list[dict]) -> list[dict]:
    """Разметка разделов инструкции, правка заголовка, удаление строки версии."""
    if blocks and blocks[0]["type"] == "p":
        blocks[0]["text"] = blocks[0]["text"].replace(
            "Инструкция по выполнению заданий", "Выполнение заданий"
        )
    out: list[dict] = []
    started = False
    for b in blocks:
        if b["type"] == "p":
            t = b["text"].strip()
            if re.match(r"^версия\s+от", t, re.I):
                continue
            if t.startswith("Приложение 1"):
                out.append({"type": "h", "text": t, "menu": "Интеллектуальные ПУ"})
                continue
            if t.startswith("Приложение 2"):
                out.append({"type": "h", "text": t, "menu": "Коды проверки"})
                continue
            if not started and re.match(r"^\d+\.", t):
                out.append({"type": "h", "text": "Действия на линии"})
                started = True
        out.append(b)
    return out


def parse_instruction_docx(content: bytes) -> list[dict]:
    """Инструкция: docx → блоки с разделами (h) и без строки версии."""
    return _postprocess_instruction(parse_docx_to_blocks(content))


def parse_task_report_docx(content: bytes) -> list[dict]:
    """«Правила проверки отчёта Алькор»: docx → заголовок + нумерованные правила (без оглавления)."""
    blocks = parse_docx_to_blocks(content)
    return [{"type": "p", "text": "Правила проверки отчёта Алькор"}] + blocks


# Контент вкладки «Операторы» (статический, без загрузки/скачивания).
OPERATOR_BLOCKS = [
    {"type": "p", "text": "Mytra: возможности операторов"},
    {"type": "h", "text": "Обзор"},
    {"type": "p", "text": "Вкладка «Обзор» — основной рабочий список заданий, доступных вашей точке учёта. Здесь вы можете:"},
    {"type": "p", "text": "— искать задание по адресу, номеру задания или лицевому счёту (поле поиска сверху);"},
    {"type": "p", "text": "— фильтровать по дате выполнения (список «Выберите дату»);"},
    {"type": "p", "text": "— фильтровать по заказчику (ПСК/РЛЭ), типу задания (плановый/внеплановый), по статусу выполнения и по наличию реестра — кликом по показателям статистики;"},
    {"type": "p", "text": "— фильтровать по виду работ и по исполнителю — кликом по строкам в списках «Вид работ» и «Исполнители»;"},
    {"type": "p", "text": "— выделять строки кликом по таблице; кнопка «Выбрать всё» выделяет все строки текущей выборки;"},
    {"type": "p", "text": "— копировать номер задания — правый клик по строке таблицы;"},
    {"type": "p", "text": "— отправлять выделенные строки в реестр кнопкой «В реестр»."},
    {"type": "h", "text": "Загрузка"},
    {"type": "p", "text": "Вкладка «Загрузка» — загрузка файла «Отчёт по заданиям ФЛ» (.xlsx). Выберите файл и дождитесь завершения; по итогу появится сводка «Загружено / Новых / Обновлено». После загрузки задания появляются во вкладке «Обзор»."},
    {"type": "h", "text": "Список"},
    {"type": "p", "text": "Вкладка «Список» — сформированные реестры. Здесь можно:"},
    {"type": "p", "text": "— выбрать реестр (плашки с номерами; пометка «(П)» — пустой реестр);"},
    {"type": "p", "text": "— найти задание по номеру или лицевому счёту (поиск с кнопкой «Сброс» переключает на реестр найденной строки);"},
    {"type": "p", "text": "— распечатать реестр, отметить реестр пустым или удалить строки из реестра."},
    {"type": "h", "text": "Настройка"},
    {"type": "p", "text": "Вкладка «Настройка» — настройка таблицы: порядок и видимость колонок (перетаскивание строк, изменения сохраняются автоматически)."},
    {"type": "h", "text": "Помощь"},
    {"type": "p", "text": "Раздел «Помощь» (в верхнем меню) — справочные материалы: «Инструкция» и «Тарифы»."},
    {"type": "p", "text": "Инструкцию и тарифы можно скачать для печати кнопкой «Скачать»: сохраняется HTML-файл — откройте его и распечатайте (Ctrl+P → «Сохранить как PDF»)."},
]


def _cell_to_str(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _read_xlsx_rows(content: bytes) -> list[list]:
    try:
        wb = CalamineWorkbook.from_filelike(io.BytesIO(content))
        sheet = wb.get_sheet_by_index(0)
        return [list(row) for row in sheet.to_python()]
    except Exception:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        return [list(row) for row in ws.iter_rows(values_only=True)]


def parse_xlsx_to_blocks(content: bytes) -> list[dict]:
    """xlsx → одна таблица (первая строка — заголовок)."""
    rows = [list(r) for r in _read_xlsx_rows(content)
            if any(c is not None and str(c).strip() for c in r)]
    if not rows:
        return []

    trimmed: list[list] = []
    for r in rows:
        while r and (r[-1] is None or str(r[-1]).strip() == ""):
            r.pop()
        trimmed.append(r)

    ncols = max(len(r) for r in trimmed)
    header = [_cell_to_str(trimmed[0][i]) if i < len(trimmed[0]) else "" for i in range(ncols)]
    header = [h if h else "Комментарий" for h in header]
    data = [[_cell_to_str(r[i]) if i < len(r) else "" for i in range(ncols)] for r in trimmed[1:]]
    return [{"type": "table", "rows": [header] + data}]


def render_help_html(title: str, blocks: list[dict]) -> str:
    """Самодостаточный HTML для печати (A4, таблицы с рамками)."""
    parts = [f"<h1>{html.escape(title)}</h1>"]
    for b in blocks:
        if b["type"] == "p":
            text = html.escape(b["text"]).replace("\n", "<br>")
            parts.append(f"<p>{text}</p>")
        elif b["type"] == "h":
            parts.append(f"<h2>{html.escape(b['text'])}</h2>")
        else:
            parts.append("<table>")
            for i, row in enumerate(b["rows"]):
                tag = "th" if i == 0 else "td"
                cells = "".join(
                    f"<{tag}>{html.escape(c).replace(chr(10), '<br>')}</{tag}>" for c in row
                )
                parts.append(f"<tr>{cells}</tr>")
            parts.append("</table>")

    body = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  @page {{ size: A4; margin: 18mm 15mm; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937; font-size: 13px; line-height: 1.55; margin: 0; }}
  h1 {{ font-size: 20px; margin: 0 0 16px; }}
  h2 {{ font-size: 16px; margin: 22px 0 8px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }}
  p {{ margin: 0 0 10px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 8px 0 16px; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; vertical-align: top; text-align: left; font-size: 12px; }}
  th {{ background: #f1f5f9; font-weight: 600; }}
  tr {{ page-break-inside: avoid; }}
</style>
</head>
<body>
{body}
</body>
</html>"""
