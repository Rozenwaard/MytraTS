"""Расчёт SLA (Приложение № 8 к Договору 226-2026) — блок полноты (результативность).

Полнота считается по домам (справочник houses):
  n_h = заказ по дому (строки base + недопуск в периоде);
  r_h = результативные строки (task_report = base);
  доля нерезультативных = 1 − Σ r_h / Σ n_h  →  ступенчатый коэффициент по шкале.
"""

import io

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


def period_like(month: str) -> str:
    """'2026-10' → '%.10.2026' (due_date хранится как 'ДД.ММ.ГГГГ')."""
    year, mon = month.split("-")
    return f"%.{mon}.{year}"


def step_coef(non_resultative_pct: float, thresholds: list) -> float:
    for upper, coef in thresholds:
        if non_resultative_pct <= upper:
            return coef
    return thresholds[-1][1]


async def compute_resultativity(db_session: AsyncSession, month: str) -> dict:
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

    return {
        "month": month,
        "rows": rows,
        "totals": {
            "base": round(total_base, 2),
            "sum_sla": round(total_sla, 2),
            "reduction": round(total_base - total_sla, 2),
        },
    }


def generate_sla_xlsx(data: dict) -> bytes:
    """Xlsx: одна вкладка «СЛА» с тремя таблицами (полнота / сроки / недопуски).

    Сроки и недопуски пока не реализованы — выводятся заглушками.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "СЛА"
    bold = Font(bold=True)

    # 1. Полнота
    ws.append(["Полнота (результативность), п. 1.1–1.4"])
    ws.cell(1, 1).font = bold
    headers = ["Код", "Работа", "Заказ", "Выполнение", "Домов", "Нерез. %",
               "Общий к-т", "Ступень", "Расценка (база)", "Расценка (СЛА)",
               "Сумма СЛА", "Потери, руб"]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        ws.cell(2, c).font = bold
    for row in data["rows"]:
        ws.append([
            row["code"], row["task_report"], row["quantity"], row["resultative"],
            row["houses"], row["non_resultative_pct"], row["smooth_coef"],
            row["sla_coef"], row["rate"], row["rate_sla"], row["sum_sla"], row["reduction"],
        ])
    ws.append(["", "Итого", "", "", "", "", "", "", "", "",
               data["totals"]["sum_sla"], data["totals"]["reduction"]])

    ws.append([])
    ws.append(["Сроки (п. 2.1, 2.2) — пока не реализовано"])
    ws.append([])
    ws.append(["Недопуски — пока не реализовано"])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
