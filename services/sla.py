"""Расчёт SLA (Приложение № 8 к Договору 226-2026) — полнота + сроки.

Полнота (п. 1.1–1.4) считается по домам (справочник houses).
Сроки (п. 2.1) — по строкам: дедлайн = created_at + 10 кал. дней (перенос на рабочий);
день дедлайна — первый день просрочки (просрочка = done_day − created_at − 9);
строки с просрочкой > 7 дней исключаются.
"""

import io
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

RESULTATIVITY = [
    {
        "code": "1.1",
        "task_report": "Плановое КСП лестница",
        "nedopusk": "Недопуск план лестница",
        "thresholds": [(10.0, 1.0), (15.0, 0.97), (float("inf"), 0.95)],
    },
    {
        "code": "1.2",
        "task_report": "Плановое КСП квартира",
        "nedopusk": "Недопуск план квартира",
        "thresholds": [(25.0, 1.0), (35.0, 0.95), (float("inf"), 0.9)],
    },
]

# Сроки (п. 2.1): работы, по которым считаем соблюдение регламентных сроков.
SROKI = [
    "Штучное КСП ФЛ", "Допуск ПУ ФЛ", "ИП ФЛ", "Проверка РО ФЛ",
    "Жалобы на качество", "Чтение архива ПСК", "Перепрограммирование ПУ", "Нагрев",
]
SROKI_THRESHOLDS = [(15.0, 1.0), (20.0, 0.95), (float("inf"), 0.9)]
DEADLINE_DAYS = 10  # дедлайн = created_at + 10 календарных дней


def period_like(month: str) -> str:
    """'2026-10' → '%.10.2026' (due_date хранится как 'ДД.ММ.ГГГГ')."""
    year, mon = month.split("-")
    return f"%.{mon}.{year}"


def step_coef(non_resultative_pct: float, thresholds: list) -> float:
    for upper, coef in thresholds:
        if non_resultative_pct <= upper:
            return coef
    return thresholds[-1][1]


def done_like(month: str) -> str:
    """'2026-10' → '2026-10%' (done_day хранится как 'ГГГГ-ММ-ДД')."""
    return f"{month}%"


def _shift_to_workday(d: date, cal: dict) -> date:
    """Перенос дедлайна на ближайший рабочий день (если выпал на выходной)."""
    while cal.get(d.isoformat()) == "Выходной":
        d += timedelta(days=1)
    return d


async def _load_calendar(db_session: AsyncSession) -> dict:
    return {r[0]: r[1] for r in (await db_session.execute(
        text("SELECT d, type FROM calendar"))).fetchall()}


async def _compute_resultativity(db_session: AsyncSession, month: str) -> tuple[list, float, float]:
    like = period_like(month)
    rows = []
    total_base = 0.0
    total_sla = 0.0

    for cfg in RESULTATIVITY:
        n, r, houses = (await db_session.execute(text("""
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN m.task_report = :base THEN 1 ELSE 0 END), 0),
                   COUNT(DISTINCT m.house_id)
            FROM main_afl m
            WHERE m.customer = 'ПСК'
              AND m.task_type = 'Плановый'
              AND m.due_date LIKE :like
              AND m.house_id IS NOT NULL
              AND m.task_report IN (:base, :nedopusk)
        """), {
            "base": cfg["task_report"],
            "nedopusk": cfg["nedopusk"],
            "like": like,
        })).one()
        n = n or 0
        r = r or 0

        price = (await db_session.execute(text(
            "SELECT price FROM work_catalog WHERE short = :s AND kind = 'base' LIMIT 1"
        ), {"s": cfg["task_report"]})).scalar() or 0.0

        smooth = (r / n) if n else 1.0
        non_resultative_pct = (1 - smooth) * 100 if n else 0.0
        sla = step_coef(non_resultative_pct, cfg["thresholds"])
        base = n * price
        sum_sla = base * sla

        total_base += base
        total_sla += sum_sla

        rate_sla = price * sla
        rows.append({
            "code": cfg["code"],
            "task_report": cfg["task_report"],
            "quantity": n,
            "resultative": r,
            "houses": houses or 0,
            "non_resultative_pct": round(non_resultative_pct, 2),
            "smooth_coef": round(smooth, 4),
            "sla_coef": sla,
            "rate": price,
            "rate_sla": round(rate_sla, 2),
            "sum_sla": round(sum_sla, 2),
            "reduction": round(base - sum_sla, 2),
        })

    return rows, total_base, total_sla


async def _compute_deadlines(db_session: AsyncSession, month: str) -> tuple[list, float, float]:
    cal = await _load_calendar(db_session)
    dl = done_like(month)
    rows = []
    total_base = 0.0
    total_sla = 0.0

    for work in SROKI:
        n = 0  # всего (просрочка <= 7 дней)
        r = 0  # в срок (просрочка <= 0)
        result = await db_session.execute(text(
            "SELECT created_at, done_day FROM main_afl "
            "WHERE customer = 'ПСК' AND task_report = :w AND done_day LIKE :d"
        ), {"w": work, "d": dl})
        for created, done_day in result.fetchall():
            if not created or not done_day:
                continue
            c = date.fromisoformat(created)
            deadline = _shift_to_workday(c + timedelta(days=DEADLINE_DAYS), cal)
            dd = date.fromisoformat(done_day)
            # день дедлайна — уже первый день просрочки:
            # просрочка = done_day − created_at − 9 (0 — в срок, 1 — день дедлайна).
            overdue = 0 if dd < deadline else (dd - deadline).days + 1
            if overdue > 7:
                continue
            n += 1
            if overdue == 0:
                r += 1

        price = (await db_session.execute(text(
            "SELECT price FROM work_catalog WHERE short = :s AND kind = 'base' LIMIT 1"
        ), {"s": work})).scalar() or 0.0

        smooth = (r / n) if n else 1.0
        non_resultative_pct = (1 - smooth) * 100 if n else 0.0
        sla = step_coef(non_resultative_pct, SROKI_THRESHOLDS)
        base = n * price
        sum_sla = base * sla

        total_base += base
        total_sla += sum_sla

        rate_sla = price * sla
        rows.append({
            "code": "2.1",
            "task_report": work,
            "quantity": n,
            "resultative": r,
            "houses": None,
            "non_resultative_pct": round(non_resultative_pct, 2),
            "smooth_coef": round(smooth, 4),
            "sla_coef": sla,
            "rate": price,
            "rate_sla": round(rate_sla, 2),
            "sum_sla": round(sum_sla, 2),
            "reduction": round(base - sum_sla, 2),
        })

    return rows, total_base, total_sla


async def compute_sla(db_session: AsyncSession, month: str) -> dict:
    res_rows, res_base, res_sla = await _compute_resultativity(db_session, month)
    dl_rows, dl_base, dl_sla = await _compute_deadlines(db_session, month)

    total_base = res_base + dl_base
    total_sla = res_sla + dl_sla

    return {
        "month": month,
        "resultativity": res_rows,
        "deadlines": dl_rows,
        "totals": {
            "base": round(total_base, 2),
            "sum_sla": round(total_sla, 2),
            "reduction": round(total_base - total_sla, 2),
        },
    }


def generate_sla_xlsx(data: dict) -> bytes:
    """Xlsx: одна вкладка «СЛА» с тремя таблицами (полнота / сроки / недопуски)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "СЛА"
    bold = Font(bold=True)

    headers = ["Код", "Работа", "Заказ", "Выполнение", "Домов", "Нерез. %",
               "Общий к-т", "Ступень", "Расценка (база)", "Расценка (СЛА)",
               "Сумма СЛА", "Потери, руб"]

    def _write_table(title: str, rows: list) -> None:
        ws.append([title])
        ws.cell(ws.max_row, 1).font = bold
        ws.append(headers)
        for c in range(1, len(headers) + 1):
            ws.cell(ws.max_row, c).font = bold
        for row in rows:
            ws.append([
                row["code"], row["task_report"], row["quantity"], row["resultative"],
                "" if row.get("houses") is None else row["houses"],
                row["non_resultative_pct"], row["smooth_coef"],
                row["sla_coef"], row["rate"], row["rate_sla"], row["sum_sla"], row["reduction"],
            ])

    _write_table("Полнота (результативность), п. 1.1–1.4", data["resultativity"])
    ws.append([])
    _write_table("Сроки (п. 2.1)", data["deadlines"])
    ws.append([])

    ws.append(["", "Итого", "", "", "", "", "", "", "", "",
               data["totals"]["sum_sla"], data["totals"]["reduction"]])
    ws.append([])
    ws.append(["Недопуски — пока не реализовано"])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
