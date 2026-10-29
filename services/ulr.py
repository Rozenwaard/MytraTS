"""Логика УЛР: матчинг строк реестра по libra и формирование строк main_afl (sand.db)."""
import base64
import io

from openpyxl import Workbook
from python_calamine import CalamineWorkbook
from sqlalchemy import text

# Колонки libra, которые нужны для матчинга и обогащения.
LIBRA_SELECT = (
    "object_code, contract_number, meter_serial_number, tu_number, tu_id, metering_point, "
    "meter_type, phase_count, tu_name, object_name, subscriber_category, subscriber_name, "
    "subscriber_short_name, address, municipal_district, region, is_mkd, contract_division, depts, grid_company"
)

INSERT_SQL = """
INSERT INTO main_afl (
    task_number, task_source, task_type, work_type_in_task, created_at, due_date,
    customer, visit_reason, subscriber_type, grid,
    metering_point, personal_account, meter_model, meter_type, meter_serial_number,
    house_type, meter_installation_place, contract_status,
    subscriber_name, address, municipal_district, region,
    service_object_type, third_party_organization, task_organization, assignee, executor_organization, status
) VALUES (
    :task_number, :task_source, :task_type, :work_type_in_task, :created_at, :due_date,
    :customer, :visit_reason, :subscriber_type, :grid,
    :metering_point, :personal_account, :meter_model, :meter_type, :meter_serial_number,
    :house_type, :meter_installation_place, :contract_status,
    :subscriber_name, :address, :municipal_district, :region,
    :service_object_type, :third_party_organization, :task_organization, :assignee, :executor_organization, :status
)
"""


# === Справочник «Выполнение» (из Книга123.xlsx, лист 2) ===

WORK_TYPE_OPTIONS = {
    "РЛЭ": {
        "КСП": {"Плановый": [1, 14], "Внеплановый": [2, 14]},
        "Архив": [3, 14],
        "ИП": {"1ф": [5, 14], "3ф": [4, 14]},
        "Опрос": [6, 14],
        "Привязка": [7, 8, 9, 14],
        "Допуск": {"1ф": [10, 14], "3ф": [11, 14]},
        "КРО": [12, 14],
    },
    "ПСК": {
        "КСП": {"Плановый": {"ИКУ": [55, 56], "ЮЛ": [57, 58]}, "Внеплановый": [59, 60]},
        "Осмотр": [61, 62],
        "Допуск": [63],
        "ИП": [64],
        "КРО": [65],
        "Доставка": [66, 67],
        "Архив": [68],
    },
}

# Виды работ, при которых 3ф-ПУ требует соисполнителя (work_catalog.id).
CO_EXECUTOR_WORK_IDS = {4, 11, 23, 24, 63, 64}

# Должности, доступные для выбора Исполнителя/Соисполнителя.
EXECUTOR_POSITIONS = ("Инженер 1 категории", "Инженер 2 категории", "Контролёр")

NO_EXECUTION = "Без исполнения"
IKU_CATEGORY = "02 Исполнители КУ"

STATUS_CREATED = "Создано"
STATUS_ASSIGNED = "Назначено"
STATUS_DONE = "Выполнено"
STATUS_SENT = "Отправлено"


def resolve_work_ids(customer, category, task_type, meter_type, subscriber_category) -> list:
    """Варианты «Вид работ» (work_catalog.id) для строки по её критериям."""
    cfg = (WORK_TYPE_OPTIONS.get(customer) or {}).get(category)
    if cfg is None:
        return []
    if isinstance(cfg, list):
        return cfg
    if customer == "РЛЭ":
        if category in ("ИП", "Допуск"):
            return cfg.get(meter_type, [])
        return cfg.get(task_type, [])
    if customer == "ПСК" and category == "КСП":
        if task_type == "Плановый":
            inner = cfg.get("Плановый") or {}
            branch = "ИКУ" if subscriber_category == IKU_CATEGORY else "ЮЛ"
            return inner.get(branch, [])
        return cfg.get(task_type, [])
    return []


def compute_status(executor, done_day, task_report, co_executor, co_executor_required, reestr_number) -> str:
    if reestr_number:
        return STATUS_SENT
    if executor and done_day and task_report and (not co_executor_required or co_executor):
        return STATUS_DONE
    if executor:
        return STATUS_ASSIGNED
    return STATUS_CREATED


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


def build_main_afl_row(p: dict, form: dict, now, head_map: dict) -> dict:
    dept = p.get("depts")
    model = p.get("meter_type")
    phase = p.get("phase_count")
    subdivision = form.get("subdivision")
    is_rle = form.get("customer") == "РЛЭ"
    return {
        "task_source": "mytra",
        "task_type": form["task_type"],
        "work_type_in_task": form["work_type_in_task"],
        "created_at": now.strftime("%Y-%m-%d"),
        "due_date": form["due_date"],
        "customer": form["customer"],
        "visit_reason": form["visit_reason"],
        "subscriber_type": "ЮЛ",
        "grid": subdivision if is_rle else p.get("grid_company"),
        "metering_point": p["tu_id"],
        "personal_account": p["metering_point"],
        "meter_model": model,
        "meter_type": {"1": "1ф", "3": "3ф"}.get(phase),
        "meter_serial_number": p["meter_serial_number"],
        "house_type": p["is_mkd"],
        "meter_installation_place": p["tu_name"],
        "contract_status": p["subscriber_category"],
        "subscriber_name": p.get("subscriber_short_name") or p.get("subscriber_name"),
        "address": p["address"],
        "municipal_district": p["municipal_district"],
        "region": p["region"],
        "service_object_type": p["object_name"],
        "third_party_organization": p["contract_division"],
        "task_organization": subdivision,
        "assignee": head_map.get(dept) if dept else None,
        "executor_organization": dept,
        "status": STATUS_CREATED,
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
