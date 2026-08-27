import io
import json
import re
from collections import defaultdict

import pandas as pd
from litestar import Router
from litestar.connection import Request
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth
from services.premium import aggregate_utalo

MAN_DAY_MINUTES = 480  # 8 часов в человеко-дне


def _read_tabel_excel(content: bytes) -> pd.DataFrame:
    """Читает табель без шапки (как в эталонном timer()): calamine, fallback openpyxl."""
    try:
        return pd.read_excel(io.BytesIO(content), header=None, engine="calamine")
    except Exception:
        return pd.read_excel(io.BytesIO(content), header=None, engine="openpyxl")


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
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _normalize_staff_id(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return s or None


def _parse_hours(value) -> float | None:
    """Из '18 (142,6)' достаёт часы 142.6."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
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
        df = _read_tabel_excel(content)
    except Exception:
        return Response(content=json.dumps({"error": "Файл не является таблицей Excel"}, ensure_ascii=False), media_type="application/json", status_code=400)

    df = df.dropna(axis=0, how="all")
    if df.shape[0] <= 7 or df.shape[1] <= 6:
        return Response(content=json.dumps({"error": "Файл не соответствует формату табеля"}, ensure_ascii=False), media_type="application/json", status_code=400)

    period = _normalize_period(df.iat[2, 6])
    if not period:
        return Response(content=json.dumps({"error": "Файл не соответствует формату табеля (не найден период)"}, ensure_ascii=False), media_type="application/json", status_code=400)

    df = df.iloc[7:]
    df = df.dropna(axis=1, how="all")
    df.columns = [f"col{j + 1}" for j in range(df.shape[1])]
    if "col2" not in df.columns or "col5" not in df.columns:
        return Response(content=json.dumps({"error": "Файл не соответствует формату табеля"}, ensure_ascii=False), media_type="application/json", status_code=400)

    by_staff: dict[str, dict] = {}
    for _, row in df.iterrows():
        staff_id = _normalize_staff_id(row.get("col2"))
        if not staff_id:
            continue
        hours = _parse_hours(row.get("col5"))
        if hours is None or hours <= 0:
            continue
        position = _blank_if_na(row.get("col4"))
        if _categorize(position) is None:
            continue  # не нужные должности не храним
        if staff_id not in by_staff:
            by_staff[staff_id] = {"name": _blank_if_na(row.get("col3")), "position": position, "minutes": 0.0}
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
    """«Добавить нормативы»: агрегирует main_afl в utalo за выбранный период."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    period = (data.get("period") or "").strip()
    if not period:
        return Response(content=json.dumps({"error": "Выберите период"}, ensure_ascii=False), media_type="application/json", status_code=400)

    rows = await aggregate_utalo(db_session, period)
    return Response(content=json.dumps({"success": True, "period": period, "rows": rows}, ensure_ascii=False), media_type="application/json")


premium_router = Router("/api", route_handlers=[api_premium_summary, api_premium_tabel, api_premium_norms])


