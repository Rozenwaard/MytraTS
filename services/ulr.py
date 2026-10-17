"""Логика УЛР: матчинг строк реестра по libra и формирование строк main_afl (sand.db)."""
import base64
import io

from openpyxl import Workbook
from python_calamine import CalamineWorkbook
from sqlalchemy import text

# Колонки libra, которые нужны для матчинга и обогащения.
LIBRA_SELECT = (
    "object_code, contract_number, meter_serial_number, tu_number, tu_id, metering_point, "
    "meter_type, tu_name, object_name, subscriber_category, subscriber_name, "
    "address, municipal_district, region"
)

INSERT_SQL = """
INSERT INTO main_afl (
    task_number, task_source, work_type_in_task, created_at, due_date,
    customer, visit_reason, subscriber_type, grid,
    metering_point, personal_account, meter_model, meter_serial_number,
    house_type, meter_installation_place, contract_status,
    subscriber_name, address, municipal_district, region
) VALUES (
    :task_number, :task_source, :work_type_in_task, :created_at, :due_date,
    :customer, :visit_reason, :subscriber_type, :grid,
    :metering_point, :personal_account, :meter_model, :meter_serial_number,
    :house_type, :meter_installation_place, :contract_status,
    :subscriber_name, :address, :municipal_district, :region
)
"""


def _cell_to_str(value):
    if value is None or value == "":
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return s or None


def read_register(content: bytes) -> list[dict]:
    """Читает аккуратный 3-колоночный файл: [0] object_code, [1] tu_number, [2] meter_serial_number.
    Первая строка — заголовок, пропускается."""
    wb = CalamineWorkbook.from_filelike(io.BytesIO(content))
    sheet = wb.get_sheet_by_index(0)
    rows = [list(r) for r in sheet.to_python()]
    if len(rows) < 2:
        return []
    out = []
    for r in rows[1:]:
        oc = _cell_to_str(r[0]) if len(r) > 0 else None
        tu = _cell_to_str(r[1]) if len(r) > 1 else None
        ms = _cell_to_str(r[2]) if len(r) > 2 else None
        if oc is None and ms is None and tu is None:
            continue
        out.append({"object_code": oc, "meter_serial_number": ms, "tu_number": tu})
    return out


async def _fetch_libra(session, where: str, params: dict) -> list[dict]:
    result = await session.execute(text(f"SELECT {LIBRA_SELECT} FROM libra WHERE {where}"), params)
    return [dict(r._mapping) for r in result]


async def find_points(session, row):
    """Каскад матчинга без догадок. Возвращает (points, reason) — точки libra или причину фидбека."""
    oc = (row["object_code"] or "").strip()
    ms = (row["meter_serial_number"] or "").strip()
    tu = (row["tu_number"] or "").strip()

    if not oc and not ms and not tu:
        return None, "нет ни объекта, ни ПУ, ни ТУ"

    if oc:
        n = len(oc)
        if n == 18:
            rows = await _fetch_libra(session, "object_code = :oc", {"oc": oc})
            if not rows:
                return None, "объект не найден"
            if ms:
                pts = [r for r in rows if r["meter_serial_number"] == ms]
                if len(pts) == 1:
                    return pts, None
                if not pts:
                    return None, "ПУ не найден в объекте"
                return None, "ПУ неоднозначен в объекте"
            if tu:
                pts = [r for r in rows if r["tu_number"] == tu]
                if len(pts) == 1:
                    return pts, None
                if not pts:
                    return None, "ТУ не найден в объекте"
                return None, "ТУ неоднозначен в объекте"
            return rows, None  # все точки объекта
        elif n == 14:
            rows = await _fetch_libra(session, "object_code LIKE :p", {"p": oc + "%"})
            if not rows:
                return None, "контракт не найден"
            if ms:
                pts = [r for r in rows if r["meter_serial_number"] == ms]
                if len(pts) == 1:
                    return pts, None
                if not pts:
                    return None, "ПУ не найден в контракте"
                return None, "ПУ неоднозначен в контракте"
            return None, "14-значный контракт без ПУ — неоднозначно"
        elif n == 6:
            rows = await _fetch_libra(session, "contract_number = :cn", {"cn": oc})
            if not rows:
                return None, "контракт не найден"
            if ms:
                pts = [r for r in rows if r["meter_serial_number"] == ms]
                if len(pts) == 1:
                    return pts, None
                if not pts:
                    return None, "ПУ не найден в контракте"
                return None, "ПУ неоднозначен в контракте"
            return None, "6-значный контракт без ПУ — неоднозначно"
        else:
            return None, f"неверная длина номера объекта ({n} знаков)"
    else:
        if ms:
            rows = await _fetch_libra(session, "meter_serial_number = :ms", {"ms": ms})
            if len(rows) == 1:
                return rows, None
            if not rows:
                return None, "ПУ не найден"
            return None, "ПУ неоднозначен"
        return None, "только ТУ без объекта — недостаточно"


def build_main_afl_row(p: dict, form: dict, now) -> dict:
    return {
        "task_number": f"{now.strftime('%Y%m%d')}_{p['tu_id'] or ''}",
        "task_source": "mytra",
        "work_type_in_task": form["work_type_in_task"],
        "created_at": now.strftime("%Y-%m-%d"),
        "due_date": form["due_date"],
        "customer": form["customer"],
        "visit_reason": form["visit_reason"],
        "subscriber_type": "ЮЛ",
        "grid": form["grid"],
        "metering_point": p["tu_id"],
        "personal_account": p["metering_point"],
        "meter_model": p["meter_type"],
        "meter_serial_number": p["meter_serial_number"],
        "house_type": p["object_name"],
        "meter_installation_place": p["tu_name"],
        "contract_status": p["subscriber_category"],
        "subscriber_name": p["subscriber_name"],
        "address": p["address"],
        "municipal_district": p["municipal_district"],
        "region": p["region"],
    }


def feedback_xlsx_b64(filename: str, feedback: list[dict]) -> str:
    """Генерирует xlsx фидбека (Файл, Строка, Объект, ПУ, ТУ, Причина) → base64."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Фидбек"
    ws.append(["Файл", "Строка", "Объект", "ПУ", "ТУ", "Причина"])
    for f in feedback:
        ws.append([filename, f.get("row"), f.get("object_code"),
                   f.get("meter_serial_number"), f.get("tu_number"), f.get("reason")])
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")
