import io
import json
import re
from collections import defaultdict

from litestar import Router
from openpyxl import load_workbook
from python_calamine import CalamineWorkbook
from litestar.connection import Request
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote

from deps import get_current_user, require_auth
from services.premium import aggregate_utalo, generate_premium_xlsx_bytes

MAN_DAY_MINUTES = 480  # 8 часов в человеко-дне


def _is_blank(value) -> bool:
    """Пустая ячейка: None или '' (как NaN у pandas)."""
    return value is None or value == ""


def _read_tabel_rows(content: bytes) -> list[list]:
    """Читает табель без шапки (как в эталонном timer()): calamine, fallback openpyxl."""
    try:
        wb = CalamineWorkbook.from_filelike(io.BytesIO(content))
        sheet = wb.get_sheet_by_index(0)
        return [list(row) for row in sheet.to_python()]
    except Exception:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        return [list(row) for row in ws.iter_rows(values_only=True)]


def _normalize_period(value) -> str | None:
    """'01.07.2026' (или дата/Timestamp) → '2026 07' (с пробелом, как report)."""
    if value is None:
        return None
    if hasattr(value, "year") and hasattr(value, "month"):
        return f"{value.year} {value.month:02d}"
    s = str(value).strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        return f"{m.group(3)} {int(m.group(2)):02d}"
    m = re.match(r"^(\d{4})-(\d{1,2})(?:-|\b|$)", s)
    if m:
        return f"{m.group(1)} {int(m.group(2)):02d}"
    return None


def _blank_if_na(value) -> str:
    if _is_blank(value):
        return ""
    return str(value).strip()


def _normalize_staff_id(value) -> str | None:
    if _is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return s or None


def _parse_hours(value) -> float | None:
    """Из '18 (142,6)' достаёт часы 142.6."""
    if _is_blank(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"\(([0-9]+(?:[.,][0-9]+)?)\)", str(value))
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _categorize(position) -> str | None:
    """Должность → категория премии (по users.position)."""
    p = (position or "").lower()
    if "контрол" in p:
        return "controllers"
    if "водител" in p:
        return "drivers"
    if "инженер" in p and "ведущ" not in p:
        return "engineers"
    return None


def _should_warn_missing(position) -> bool:
    """Предупреждаем об отсутствии в users только по инженерам и контролёрам."""
    p = (position or "").lower()
    return "инженер" in p or "контрол" in p


@get("/premium/summary", guards=[require_auth])
async def api_premium_summary(request: Request, db_session: AsyncSession, period: str = "") -> Response:
    """Сводка вкладки «Премия»: список периодов + плашки по выбранному периоду."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    periods = [r[0] for r in (await db_session.execute(
        text("SELECT DISTINCT period FROM tabel WHERE period IS NOT NULL ORDER BY period DESC")))]
    effective = period.strip() if period else None
    if effective not in periods:
        effective = periods[0] if periods else None

    cards = {
        "engineers": {"count": 0, "man_days": 0},
        "controllers": {"count": 0, "man_days": 0},
        "drivers": {"count": 0, "man_days": 0},
    }
    missing: list[dict] = []
    if effective:
        rows = await db_session.execute(
            text("SELECT t.staff_id, t.name, t.position, t.minutes, u.staff_id AS u_sid FROM tabel t LEFT JOIN users u ON u.staff_id = t.staff_id WHERE t.period = :p"),
            {"p": effective})
        staff_sets: dict[str, set] = defaultdict(set)
        minutes_sum: dict[str, float] = defaultdict(float)
        missing_rows: dict[str, dict] = {}
        for staff_id, name, t_position, minutes, u_sid in rows:
            if u_sid is None:
                # строка в tabel, но такого staff_id нет в users
                if staff_id and _should_warn_missing(t_position):
                    missing_rows[staff_id] = {"staff_id": staff_id, "name": name or "", "position": t_position or ""}
            cat = _categorize(t_position)  # категория по должности из файла
            if cat is None:
                continue
            if staff_id:
                staff_sets[cat].add(staff_id)
            minutes_sum[cat] += (minutes or 0)
        for cat in cards:
            cards[cat]["count"] = len(staff_sets[cat])
            cards[cat]["man_days"] = round(minutes_sum[cat] / MAN_DAY_MINUTES)
        missing = sorted(missing_rows.values(), key=lambda m: m["staff_id"])

    return Response(content=json.dumps({
        "period": effective, "periods": periods, "cards": cards, "missing": missing,
    }, ensure_ascii=False), media_type="application/json")


@post("/premium/tabel", guards=[require_auth])
async def api_premium_tabel(
    request: Request, db_session: AsyncSession,
    data: UploadFile = Body(media_type=RequestEncodingType.MULTI_PART),
) -> Response:
    """«Добавить табель»: xlsx/xls → таблица tabel (табельный номер, период, минуты)."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    if not data or not data.filename.lower().endswith((".xlsx", ".xls")):
        return Response(content=json.dumps({"error": "Нужен файл .xlsx или .xls"}, ensure_ascii=False), media_type="application/json", status_code=400)

    content = await data.read()
    try:
        rows = _read_tabel_rows(content)
    except Exception:
        return Response(content=json.dumps({"error": "Файл не является таблицей Excel"}, ensure_ascii=False), media_type="application/json", status_code=400)

    # Убираем полностью пустые строки
    rows = [r for r in rows if any(not _is_blank(v) for v in r)]
    num_rows = len(rows)
    num_cols = max((len(r) for r in rows), default=0)
    if num_rows <= 7 or num_cols <= 6:
        return Response(content=json.dumps({"error": "Файл не соответствует формату табеля"}, ensure_ascii=False), media_type="application/json", status_code=400)

    period = _normalize_period(rows[2][6] if len(rows[2]) > 6 else None)
    if not period:
        return Response(content=json.dumps({"error": "Файл не соответствует формату табеля (не найден период)"}, ensure_ascii=False), media_type="application/json", status_code=400)

    data = rows[7:]

    # Убираем полностью пустые колонки (в строках данных)
    keep = [c for c in range(num_cols) if any(c < len(r) and not _is_blank(r[c]) for r in data)]
    if len(keep) < 5:
        return Response(content=json.dumps({"error": "Файл не соответствует формату табеля"}, ensure_ascii=False), media_type="application/json", status_code=400)

    def cell(row, kept_idx):
        pos = keep[kept_idx]
        return row[pos] if pos < len(row) else None

    by_staff: dict[str, dict] = {}
    for row in data:
        staff_id = _normalize_staff_id(cell(row, 1))
        if not staff_id:
            continue
        hours = _parse_hours(cell(row, 4))
        if hours is None or hours <= 0:
            continue
        position = _blank_if_na(cell(row, 3))
        if _categorize(position) is None:
            continue  # не нужные должности не храним
        if staff_id not in by_staff:
            by_staff[staff_id] = {"name": _blank_if_na(cell(row, 2)), "position": position, "minutes": 0.0}
        by_staff[staff_id]["minutes"] += round(hours * 60, 2)

    if not by_staff:
        return Response(content=json.dumps({"error": "Файл не соответствует формату табеля (нет строк с часами)"}, ensure_ascii=False), media_type="application/json", status_code=400)

    # Храним только нужные должности (инженеры без ведущих, контролёры, водители).
    await db_session.execute(text("DELETE FROM tabel WHERE period = :p"), {"p": period})
    for staff_id, info in by_staff.items():
        await db_session.execute(
            text("INSERT INTO tabel (staff_id, period, minutes, position, name) VALUES (:s, :p, :m, :pos, :name)"),
            {"s": staff_id, "p": period, "m": info["minutes"], "pos": info["position"], "name": info["name"]})
    await db_session.commit()

    return Response(content=json.dumps({
        "success": True, "period": period, "stored": len(by_staff),
    }, ensure_ascii=False), media_type="application/json")


@post("/premium/norms", guards=[require_auth])
async def api_premium_norms(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Отчёт по нормативам»: агрегирует текущие main_afl в utalo (все строки с norm/extra)."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    rows = await aggregate_utalo(db_session)
    return Response(content=json.dumps({"success": True, "rows": rows}, ensure_ascii=False), media_type="application/json")


@get("/premium/download", guards=[require_auth])
async def api_premium_download(request: Request, db_session: AsyncSession, period: str = "") -> Response:
    """Скачивает отчёт по нормативам из utalo за период (вкладки: Алькор / Проект)."""
    await get_current_user(request, db_session)
    if not period:
        return Response(content=json.dumps({"error": "Выберите период"}, ensure_ascii=False), media_type="application/json", status_code=400)

    alcor_rows = (await db_session.execute(text(
        "SELECT full_name, position, dept, task_report, count, norm_sum FROM utalo "
        "WHERE period = :p AND task_report IN (SELECT title FROM carte WHERE kind = 'base') "
        "ORDER BY full_name, task_report"
    ), {"p": period})).fetchall()

    project_rows = (await db_session.execute(text(
        "SELECT full_name, position, dept, task_report, count, norm_sum FROM utalo "
        "WHERE period = :p AND task_report NOT IN (SELECT title FROM carte WHERE kind = 'base') "
        "ORDER BY full_name, task_report"
    ), {"p": period})).fetchall()

    output = generate_premium_xlsx_bytes(alcor_rows, project_rows)
    filename = f"Отчёт_по_нормативам_{period.replace(' ', '_')}.xlsx"
    return Response(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


premium_router = Router("/api", route_handlers=[api_premium_summary, api_premium_tabel, api_premium_norms, api_premium_download])


