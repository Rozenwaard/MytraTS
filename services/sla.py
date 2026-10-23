"""Расчёт SLA (Договор 226-2026) — парные работы (успех / недопуск).

По каждой парной работе: заказ = выполнение + недопуск (по due_date).
Полнота = ступенчатый к-т от доли недопусков (недопуск / заказ).
Сроки = к-т 2.1 (по done_day, только для работ с регламентным сроком).
Коэффициент = min(полнота, сроки); потери = заказ × базовая расценка × (1 − коэф);
оверкэп = max(0, недопуск − лимит) × расценка недопуска.
"""

import io
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Парные работы (ФЛ, ПСК): база ↔ недопуск + лимит недопусков (вкладка «Недопуски»).
PAIRED_WORKS = [
    {
        "task_report": "Плановое КСП лестница",
        "nedopusk": "Недопуск план лестница",
        "limit_pct": 10.0,
        "thresholds": [(10.0, 1.0), (15.0, 0.97), (float("inf"), 0.95)],
    },
    {
        "task_report": "Плановое КСП квартира",
        "nedopusk": "Недопуск план квартира",
        "limit_pct": 46.0,
        "thresholds": [(25.0, 1.0), (35.0, 0.95), (float("inf"), 0.9)],
    },
    {
        "task_report": "Штучный план",
        "nedopusk": "Недопуск штучный план",
        "limit_pct": 70.0,
        "thresholds": [(40.0, 1.0), (70.0, 0.95), (float("inf"), 0.9)],
    },
    {
        "task_report": "Штучное КСП ФЛ",
        "nedopusk": "Недопуск штучное КСП ФЛ",
        "limit_pct": 10.0,
        "thresholds": [(10.0, 1.0), (15.0, 0.95), (float("inf"), 0.9)],
    },
    {
        "task_report": "Чтение архива ПСК",
        "nedopusk": "Недопуск чтение архива",
        "limit_pct": 30.0,
        "thresholds": [(10.0, 1.0), (15.0, 0.95), (float("inf"), 0.9)],
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


async def _compute_sroki_coefs(db_session: AsyncSession, month: str) -> dict:
    """Коэффициенты 2.1 по работам с регламентным сроком: {работа: к-т}."""
    cal = await _load_calendar(db_session)
    dl = done_like(month)
    result = {}
    for work in SROKI:
        n = 0  # всего (просрочка <= 7 дней)
        r = 0  # в срок (просрочка <= 0)
        rows = (await db_session.execute(text(
            "SELECT created_at, done_day FROM main_afl "
            "WHERE customer = 'ПСК' AND task_report = :w AND done_day LIKE :d"
        ), {"w": work, "d": dl})).fetchall()
        for created, done_day in rows:
            if not created or not done_day:
                continue
            c = date.fromisoformat(created)
            deadline = _shift_to_workday(c + timedelta(days=DEADLINE_DAYS), cal)
            dd = date.fromisoformat(done_day)
            # день дедлайна — уже первый день просрочки (просрочка = done_day − created_at − 9).
            overdue = 0 if dd < deadline else (dd - deadline).days + 1
            if overdue > 7:
                continue
            n += 1
            if overdue == 0:
                r += 1
        smooth = (r / n) if n else 1.0
        non_resultative_pct = (1 - smooth) * 100 if n else 0.0
        result[work] = step_coef(non_resultative_pct, SROKI_THRESHOLDS)
    return result


async def compute_sla(db_session: AsyncSession, month: str) -> dict:
    sroki_coefs = await _compute_sroki_coefs(db_session, month)
    like = period_like(month)
    rows = []
    total_loss = 0.0
    total_overcap = 0.0

    for cfg in PAIRED_WORKS:
        base = cfg["task_report"]
        nedopusk = cfg["nedopusk"]
        n, r = (await db_session.execute(text("""
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN task_report = :base THEN 1 ELSE 0 END), 0)
            FROM main_afl
            WHERE customer = 'ПСК'
              AND due_date LIKE :like
              AND task_report IN (:base, :nedopusk)
        """), {
            "base": base,
            "nedopusk": nedopusk,
            "like": like,
        })).one()
        n = n or 0
        r = r or 0
        ned = n - r  # недопуск

        prices = {row[0]: row[1] for row in (await db_session.execute(text(
            "SELECT short, price FROM work_catalog WHERE short IN (:b, :n)"
        ), {"b": base, "n": nedopusk})).fetchall()}
        base_price = prices.get(base) or 0.0
        ned_price = prices.get(nedopusk) or 0.0

        limit = int(cfg["limit_pct"] / 100.0 * r)  # лимит = доля × выполнение, вниз до целого
        non_resultative_pct = (ned / n * 100) if n else 0.0
        fullness = step_coef(non_resultative_pct, cfg["thresholds"])
        sroki = sroki_coefs.get(base, 1.0)
        coef = min(fullness, sroki)

        loss = n * base_price * (1 - coef)
        overcap = max(0.0, ned - limit) * ned_price

        total_loss += loss
        total_overcap += overcap

        rows.append({
            "task_report": base,
            "quantity": n,               # заказ
            "resultative": r,            # выполнение
            "nedopusk": ned,             # недопуск
            "limit": limit,              # лимит = доля × выполнение (целое)
            "fullness": fullness,        # полнота
            "sroki": sroki,              # сроки
            "coef": coef,                # min(полнота, сроки)
            "loss": round(loss, 2),      # потери
            "overcap": round(overcap, 2),  # оверкэп
        })

    return {
        "month": month,
        "rows": rows,
        "totals": {
            "loss": round(total_loss, 2),
            "overcap": round(total_overcap, 2),
            "total": round(total_loss + total_overcap, 2),
        },
    }


def generate_sla_xlsx(data: dict) -> bytes:
    """Xlsx: вкладка «СЛА» — таблица парных работ + итог по потерям/оверкэпу."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "СЛА"
    bold = Font(bold=True)

    headers = ["Работа", "Заказ", "Выполнение", "Недопуск", "Лимит",
               "Полнота", "Сроки", "Коэффициент", "Потери", "Оверкэп"]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        ws.cell(1, c).font = bold

    for row in data["rows"]:
        ws.append([
            row["task_report"], row["quantity"], row["resultative"], row["nedopusk"],
            row["limit"], row["fullness"], row["sroki"], row["coef"],
            row["loss"], row["overcap"],
        ])

    ws.append(["Итого", "", "", "", "", "", "", "",
               data["totals"]["loss"], data["totals"]["overcap"]])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
