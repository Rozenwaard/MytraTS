"""Логика эксперимента РКС: парсинг РКС.xlsx + маппинг РКС УЛР.xlsx и накопление
потребителей/точек/заданий в sand.db.

РКС.xlsx (12 колонок): 0 фл/юл, 1 отделение, 2 месяц, 3 № договора, 4 наименование,
5 адрес, 6 № ПУ, 7 вид работы, 8 телефон, 9 примечание, 10 исх. № письма,
11 «дата выполнения» — мусор (игнорируем).

РКС УЛР.xlsx: L (11) «Код энергообъекта», N (13) «Дата работ», U (20) «Адрес объекта».
Сопоставление даты — по коду (договору), при неоднозначности/отсутствии — по адресу.
"""
import io
from pathlib import Path

from python_calamine import CalamineWorkbook
from sqlalchemy import text

STATUS_CREATED = "Создано"
STATUS_ASSIGNED = "Назначено"
STATUS_MP = "Доставлено на МП"
STATUS_IN_WORK = "В работе"
STATUS_DONE = "Выполнено"
STATUS_SENT = "Отправлено"

# Каталог фото мобильного контура (файлы на диске, в БД — путь + sha256).
PHOTOS_DIR = str(Path(__file__).resolve().parent.parent / "data" / "rks_photos")

# Должности, доступные для выбора Исполнителя/Соисполнителя (как в УЛР).
EXECUTOR_POSITIONS = ("Инженер 1 категории", "Инженер 2 категории", "Контролёр")
# Поручения РКС (регистрация/загрузка) — грубые категории. Конкретная работа (short из
# work_catalog) определяется на отчёте по доп. параметрам (плановый/текущий, 1ф/3ф, КЛ/ВЛ).
WORK_TYPES = ("Проверка", "Инструментальная проверка", "Чтение архива", "Привязка",
              "Идентификация", "Допуск ПУ", "Проверка РО")

# Название доптарифа «электронный отчёт» в work_catalog (+5 минут) — как в main_afl.
ALCOR_TITLE = "Выполнение задания в Алькоре"

# Виды справочников мобильного отчёта (rks_dict.kind).
DICT_KINDS = ("act_type", "additional_work", "return_reason", "violation_group")

# RKS-работы = работы РЛЭ (work_catalog.customer='РЛЭ'). Записи ПСК — на вырост, в РКС не используем.

MONTHS = {
    "январь": "Январь", "февраль": "Февраль", "март": "Март", "апрель": "Апрель",
    "май": "Май", "июнь": "Июнь", "июль": "Июль", "август": "Август",
    "сентябрь": "Сентябрь", "октябрь": "Октябрь", "ноябрь": "Ноябрь", "декабрь": "Декабрь",
}

# Синонимы из РКС.xlsx → поручение.
WORK_TYPE_NORM = {
    "кссп": "Проверка",
    "ксп": "Проверка",
    "инструментальная проверка": "Инструментальная проверка",
    "инстр": "Инструментальная проверка",
    "проверка": "Инструментальная проверка",  # «Проверка» в РКС.xlsx — сокращение инструментальной
    "чтение архива": "Чтение архива",
    "архив": "Чтение архива",
    "привязка": "Привязка",
    "идентификация": "Идентификация",
    "допуск": "Допуск ПУ",
    "допуск пу": "Допуск ПУ",
    "проверка ро": "Проверка РО",
    "опломбировка": "Проверка",       # допработа — базовое поручение «Проверка»
    "распломбировка": "Проверка",
}

# Поручение → конкретная работа (short из work_catalog) по параметрам проверки.
PORUCHENIE_TO_SHORT = {
    "Проверка": {"плановый": "Массовое КСП", "текущий": "Штучное КСП"},
    "Инструментальная проверка": {"1ф": "Инструментальная проверка 1ф", "3ф": "Инструментальная проверка 3ф"},
    "Чтение архива": "Чтение архива РЛЭ",
    "Привязка": {"КЛ": "Привязка КЛ", "ВЛ": "Привязка ВЛ"},
    "Идентификация": "Идентификация",
    "Допуск ПУ": {"1ф": "Допуск ПУ 1ф", "3ф": "Допуск ПУ 3ф"},
    "Проверка РО": "Проверка РО РЛЭ",
}


def resolve_short(poruchenie, task_type=None, phase=None, line_type=None):
    """Поручение + параметры проверки → конкретная работа (short из work_catalog)."""
    m = PORUCHENIE_TO_SHORT.get(poruchenie)
    if m is None:
        return poruchenie
    if isinstance(m, str):
        return m
    if poruchenie == "Проверка":
        key = "плановый" if (task_type or "").strip().lower() == "плановый" else "текущий"
        return m.get(key, "Штучное КСП")
    if poruchenie == "Привязка":
        return m.get(line_type, "Привязка ВЛ")
    # Инструментальная проверка / Допуск ПУ — по фазе ПУ (1ф/3ф)
    return m.get(phase, m["1ф"])

# Колонки РКС.xlsx по индексу (11-ю «Дата выполнения» пропускаем).
RKS_COLUMNS = ["fl_yul", "department", "month", "contract_number", "consumer_name",
               "address", "meter_serial", "work_type", "phone", "note", "letter_number"]


def _cell_to_str(value):
    """Пустая ячейка/'' → None, целый float → '123' (без '.0'), иначе str без краёв."""
    if value is None or value == "":
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return s or None


def _clean(value):
    """NBSP → обычный пробел + схлопывание серий пробелов (для адресов/имён)."""
    if value is None:
        return None
    s = str(value)
    for ch in ("\xa0", "\u2007", "\u202f"):
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    return s or None


def normalize_month(value):
    v = _cell_to_str(value)
    if not v:
        return None
    return MONTHS.get(v.lower(), v)


def normalize_work_type(value):
    v = _cell_to_str(value)
    if not v:
        return None
    return WORK_TYPE_NORM.get(v.lower(), v)


def parse_rks(content: bytes) -> list[dict]:
    wb = CalamineWorkbook.from_filelike(io.BytesIO(content))
    sheet = wb.get_sheet_by_index(0)
    rows = [list(r) for r in sheet.to_python()]
    if len(rows) < 2:
        return []
    out = []
    for r in rows[1:]:
        rec = {}
        for i, name in enumerate(RKS_COLUMNS):
            rec[name] = _cell_to_str(r[i]) if i < len(r) else None
        if not any(rec.get(k) for k in ("contract_number", "consumer_name", "meter_serial", "address")):
            continue
        rec["address"] = _clean(rec.get("address"))
        rec["consumer_name"] = _clean(rec.get("consumer_name"))
        out.append(rec)
    return out


def parse_rks_ulr(content: bytes) -> list[dict]:
    wb = CalamineWorkbook.from_filelike(io.BytesIO(content))
    sheet = wb.get_sheet_by_index(0)
    rows = [list(r) for r in sheet.to_python()]
    if len(rows) < 2:
        return []
    out = []
    for r in rows[1:]:
        code = _cell_to_str(r[11]) if len(r) > 11 else None
        date = _cell_to_str(r[13]) if len(r) > 13 else None
        address = _clean(r[20]) if len(r) > 20 else None
        if code is None and date is None:
            continue
        out.append({"energy_object_code": code, "work_date": date, "address": address})
    return out


def build_ulr_index(ulr_rows: list[dict]) -> tuple[dict, dict]:
    by_code: dict = {}
    by_addr: dict = {}
    for r in ulr_rows:
        code = r.get("energy_object_code")
        addr = r.get("address")
        if code:
            by_code.setdefault(code, []).append(r)
        if addr:
            by_addr.setdefault(addr, []).append(r)
    return by_code, by_addr


def match_work_date(contract_number, address, by_code, by_addr):
    """Возвращает (work_date, match_source). match_source: 'code' | 'address' | None."""
    code = _cell_to_str(contract_number)
    addr = _clean(address)

    if code:
        cands = by_code.get(code, [])
        dates = {c["work_date"] for c in cands if c.get("work_date")}
        if len(dates) == 1:
            return next(iter(dates)), "code"
        if len(dates) > 1 and addr:
            sub = [c for c in cands if c.get("address") == addr]
            sdates = {c["work_date"] for c in sub if c.get("work_date")}
            if len(sdates) == 1:
                return next(iter(sdates)), "address"

    if addr:
        cands = by_addr.get(addr, [])
        dates = {c["work_date"] for c in cands if c.get("work_date")}
        if len(dates) == 1:
            return next(iter(dates)), "address"

    return None, None


async def ingest_rks(sand_session, rks_rows, ulr_rows, source_file, now) -> dict:
    """Накопление потребителей/точек/заданий. Возвращает статистику."""
    by_code, by_addr = build_ulr_index(ulr_rows)
    year_suffix = now.strftime("%y")
    created = now.strftime("%Y-%m-%d %H:%M:%S")

    existing = (await sand_session.execute(text(
        "SELECT task_number FROM rks_task WHERE task_number LIKE :p"),
        {"p": f"%-{year_suffix}"})).fetchall()
    seq = max((int(n[0].split("-")[0]) for n in existing
               if n[0] and "-" in n[0] and n[0].split("-")[0].isdigit()), default=0)

    consumer_cache: dict = {}
    point_cache: dict = {}
    stats = {"consumers": 0, "points": 0, "tasks": 0,
             "matched_code": 0, "matched_address": 0, "unmatched": 0}

    for i, row in enumerate(rks_rows, start=2):
        contract = _cell_to_str(row.get("contract_number"))
        name = row.get("consumer_name")
        address = row.get("address")
        meter = _cell_to_str(row.get("meter_serial"))

        # --- потребитель (ключ: договор; фолбэк в рамках файла — имя/адрес) ---
        ckey = contract or name or address or None
        consumer_id = consumer_cache.get(ckey) if ckey else None
        if consumer_id is None:
            if contract:
                consumer_id = (await sand_session.execute(text(
                    "SELECT id FROM rks_consumer WHERE contract_number = :c"),
                    {"c": contract})).scalar()
            if consumer_id is None:
                eoc = contract if contract and len(contract) == 10 else None
                result = await sand_session.execute(text(
                    "INSERT INTO rks_consumer (contract_number, energy_object_code, fl_yul, "
                    "department, consumer_name, phone, created_at, updated_at, source_file, source_row) "
                    "VALUES (:contract_number, :energy_object_code, :fl_yul, :department, "
                    ":consumer_name, :phone, :created_at, :updated_at, :source_file, :source_row)"),
                    {"contract_number": contract, "energy_object_code": eoc,
                     "fl_yul": _cell_to_str(row.get("fl_yul")),
                     "department": _cell_to_str(row.get("department")),
                     "consumer_name": name,
                     "phone": _cell_to_str(row.get("phone")),
                     "created_at": created, "updated_at": created,
                     "source_file": source_file, "source_row": i})
                consumer_id = result.lastrowid
                stats["consumers"] += 1
            if ckey:
                consumer_cache[ckey] = consumer_id

        # --- точка (ключ: потребитель + адрес + ПУ) ---
        pkey = (consumer_id, address or "", meter or "")
        point_id = point_cache.get(pkey)
        if point_id is None:
            point_id = (await sand_session.execute(text(
                "SELECT id FROM rks_consumer_point "
                "WHERE consumer_id = :cid AND address IS :addr AND meter_serial IS :meter"),
                {"cid": consumer_id, "addr": address, "meter": meter})).scalar()
            if point_id is None:
                result = await sand_session.execute(text(
                    "INSERT INTO rks_consumer_point (consumer_id, address, meter_serial, "
                    "created_at, source_file, source_row) "
                    "VALUES (:consumer_id, :address, :meter_serial, :created_at, :source_file, :source_row)"),
                    {"consumer_id": consumer_id, "address": address, "meter_serial": meter,
                     "created_at": created, "source_file": source_file, "source_row": i})
                point_id = result.lastrowid
                stats["points"] += 1
            point_cache[pkey] = point_id

        # --- задание (каждая строка файла = одно задание) ---
        work_date, match_source = match_work_date(contract, address, by_code, by_addr)
        seq += 1
        task_number = f"{seq}-{year_suffix}"
        await sand_session.execute(text(
            "INSERT INTO rks_task (point_id, task_number, month, work_type, work_type_raw, "
            "note, letter_number, work_date, match_source, status, created_at, source_file, source_row) "
            "VALUES (:point_id, :task_number, :month, :work_type, :work_type_raw, :note, "
            ":letter_number, :work_date, :match_source, :status, :created_at, :source_file, :source_row)"),
            {"point_id": point_id, "task_number": task_number,
             "month": normalize_month(row.get("month")),
             "work_type": normalize_work_type(row.get("work_type")),
             "work_type_raw": _cell_to_str(row.get("work_type")),
             "note": _cell_to_str(row.get("note")),
             "letter_number": _cell_to_str(row.get("letter_number")),
             "work_date": work_date, "match_source": match_source,
             "status": STATUS_CREATED, "created_at": created,
             "source_file": source_file, "source_row": i})
        stats["tasks"] += 1
        if match_source == "code":
            stats["matched_code"] += 1
        elif match_source == "address":
            stats["matched_address"] += 1
        else:
            stats["unmatched"] += 1

    return stats


