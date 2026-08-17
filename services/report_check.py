# -*- coding: utf-8 -*-
"""
Проверка выгрузки «Алькор» — порт логики city.py (раздел 7) под main_afl.

Соответствие полей main_afl колонкам Excel («Структура отчёта Алькора.xlsx», вкладка 2026):
    BX -> work_type                BY -> work_result
    CT -> work_start_date          CU -> work_end_date
    BU -> unauthorized_connection  BS -> meter_malfunction
    BT -> unauthorized_interference BV -> additional_violations
    BQ -> violations               BR -> meter_status_date
    CR -> acts                     AB -> manufacture_year
    BC -> manufacture_year_1       AC -> last_verification_date
    BD -> last_verification_date_1 AL -> meter_ownership
    BL -> meter_ownership_1        AM -> active_disconnection
    AR -> last_readings_t1_control AS -> last_readings_t2_control
    AT -> last_readings_t3_control BN -> t1
    BO -> t2                       BP -> t3
    Y  -> meter_type               AA -> meter_serial_number
    BZ -> meter_type_2             CA -> meter_model_2
    CG -> fractional_capacity_2    CL -> meter_ownership_2
    CF -> integer_capacity_2       CI -> rated_current_2
    CJ -> rated_voltage_2          CM -> seals_2
"""

import math
import re
from datetime import date, datetime, timedelta
from typing import Any, Iterable
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ─── Константы правил (из city.py) ────────────────────────────

PU_ADMISSION_WORK_TYPES = {
    "допуск пу",
    "замена/установка",
    "установка/замена",
}

PU_ADMISSION_IMPOSSIBLE_TEXT = "невозможно выполнить допуск пу"
WORK_COMPLETED_RESULT = "работа выполнена"

ALLOWED_NEW_BALANCE_CL = {
    "Сч.собств.аб._ИСУ",
    "Сч.собств.аб.",
    "Сч.собств.ПСК_ИСУ",
    "Сч.собств.ПСК",
}

ECR_TYPES = {
    "эу-20м-33",
    "эу20",
    "эу20м-12",
    "эу 20м-32 muz",
    "эу 20м-33 mr",
    "эцр-2400",
}

RESTRICTION_ACT_TEXT = "акт проверки введенного режима ограничения"

READING_RULES = [
    ("last_readings_t1_control", "t1", "показания ДТ"),
    ("last_readings_t2_control", "t2", "показания НТ"),
    ("last_readings_t3_control", "t3", "Третий тариф"),
]

ERRORS_SEPARATOR = "; "

# Ошибки по балансовой принадлежности обрабатываются особо (не стоп-фактор).
BALANCE_ERRORS = {
    "Балансовая принадлежность",
    "Балансовая принадлежность нового ПУ",
}

# Регионы/районы, где стоп-фактор активен сейчас.
# Позже: все задания ПСК, затем все задания.
STOP_FACTOR_REGIONS = {"СПб"}
STOP_FACTOR_DISTRICTS = {"ЛО Гатчинский муниципальный район"}


# ─── Вспомогательные функции (из city.py, без pandas) ─────────
def norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    text = str(value).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def norm_key(value: Any) -> str:
    return norm_text(value).lower()


def is_empty(value: Any) -> bool:
    text = norm_text(value)
    return text == "" or text.lower() in {"nan", "nat", "none", "null"}


def is_filled(value: Any) -> bool:
    return not is_empty(value)


def is_dash_or_empty(value: Any) -> bool:
    text = norm_text(value)
    return text == "" or text == "-"


def is_yes(value: Any) -> bool:
    return norm_key(value) in {"да", "yes", "true", "1"}


def is_no(value: Any) -> bool:
    return norm_key(value) in {"нет", "no", "false", "0"}


def norm_work_key(value: Any) -> str:
    text = norm_key(value)
    return re.sub(r"\s*/\s*", "/", text)


def to_number(value: Any) -> float | None:
    if is_empty(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = norm_text(value).replace(" ", "").replace("\xa0", "").replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)

    if text in {"", "-", ".", "-."}:
        return None

    try:
        return float(text)
    except ValueError:
        return None


def to_four_digit_year(value: Any) -> int | None:
    if is_empty(value):
        return None

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)

        if number.is_integer() and 1000 <= number <= 9999:
            return int(number)

        return None

    text = norm_text(value)

    if re.fullmatch(r"\d{4}", text):
        return int(text)

    return None


def to_date(value: Any) -> date | None:
    if is_empty(value):
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Excel-серийный номер даты (система 1900)
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
        except (OverflowError, ValueError):
            return None

    text = norm_text(value)

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    # Фолбэк: «ДД.ММ.ГГГГ» / «ДД/ММ/ГГГГ» (dayfirst)
    m = re.search(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None

    return None


def is_excel_fake_date_1899(value: Any) -> bool:
    dt = to_date(value)
    return dt is not None and dt.year == 1899 and dt.month == 12 and dt.day == 31


def contains_any(value: Any, needles: Iterable[str]) -> bool:
    text = norm_key(value)
    return any(norm_key(n) in text for n in needles)


def contains_brackets(value: Any) -> bool:
    text = norm_text(value)
    return "(" in text or ")" in text


def first_two_digits(value: Any) -> str:
    text = norm_text(value)
    digits = re.sub(r"\D", "", text)
    return digits[:2] if len(digits) >= 2 else ""


def year_to_last_two(value: Any) -> str:
    if is_empty(value):
        return ""

    if isinstance(value, (datetime, date)):
        return str(value.year)[-2:]

    text = norm_text(value)

    m = re.search(r"(19|20)\d{2}", text)
    if m:
        return m.group(0)[-2:]

    digits = re.sub(r"\D", "", text)

    if len(digits) >= 4:
        return digits[-2:]
    if len(digits) == 2:
        return digits

    return ""


def add_error(errors: list, error: str) -> None:
    if error and error not in errors:
        errors.append(error)


def join_errors(errors: list) -> str:
    return ERRORS_SEPARATOR.join(errors)


def split_errors(value: Any) -> list:
    if is_empty(value):
        return []
    return [e.strip() for e in str(value).split(ERRORS_SEPARATOR) if e.strip()]


def has_stop_factor(errors: list) -> bool:
    return any(e not in BALANCE_ERRORS for e in errors)


def is_stop_blocked(row: dict) -> bool:
    """Стоп-фактор активен: регион/район в списке И есть не-балансовая ошибка."""
    if row.get("region") not in STOP_FACTOR_REGIONS and row.get("municipal_district") not in STOP_FACTOR_DISTRICTS:
        return False
    errors = split_errors(row.get("errors") or "")
    return has_stop_factor(errors)


# ─── Проверки (из city.py, раздел 7) ──────────────────────────
def check_year_by_serial(errors: list, pu_type: Any, serial: Any, year: Any) -> None:
    pu_type_key = norm_key(pu_type)

    if pu_type_key not in ECR_TYPES:
        return

    serial_yy = first_two_digits(serial)
    year_yy = year_to_last_two(year)

    if serial_yy and year_yy and year_yy != serial_yy:
        add_error(errors, "Год выпуска 2")


def check_row(row: dict) -> list:
    errors = []

    work_bx = norm_work_key(row.get("work_type"))
    result_by = norm_key(row.get("work_result"))
    is_pu_admission_work = work_bx in PU_ADMISSION_WORK_TYPES
    is_work_completed = result_by == WORK_COMPLETED_RESULT
    is_pu_admission_impossible = PU_ADMISSION_IMPOSSIBLE_TEXT in result_by
    bn_must_be_empty = is_pu_admission_work and is_work_completed

    # Дата начала и окончания работы должны быть одной датой
    date_start = to_date(row.get("work_start_date"))
    date_end = to_date(row.get("work_end_date"))

    if date_start is None or date_end is None or date_start != date_end:
        add_error(errors, "Дата работ")

    # Дата состояния ПУ не нужна, если заполнено только BU или только BV.
    # Эти исключения приоритетнее общего правила BQ = Да.
    only_bu_violation = (
        is_filled(row.get("unauthorized_connection"))
        and all(is_empty(row.get(col)) for col in ("meter_malfunction", "unauthorized_interference", "additional_violations"))
    )
    only_bv_violation = (
        is_filled(row.get("additional_violations"))
        and all(is_empty(row.get(col)) for col in ("meter_malfunction", "unauthorized_interference", "unauthorized_connection"))
    )
    br_must_be_empty = is_no(row.get("violations")) or only_bu_violation or only_bv_violation

    if br_must_be_empty:
        if is_filled(row.get("meter_status_date")):
            add_error(errors, "Зачем дата неисправности?")
    elif is_yes(row.get("violations")) and is_empty(row.get("meter_status_date")):
        add_error(errors, "Дата неисправности")

    # При BQ = Да акт нужен и для исключений, в которых BR не заполняется.
    if is_yes(row.get("violations")):
        if is_empty(row.get("acts")):
            add_error(errors, "Приложить акт")

    # Год выпуска: AB пустой и BC пустой -> ошибка
    if is_empty(row.get("manufacture_year")) and is_empty(row.get("manufacture_year_1")):
        add_error(errors, "Год выпуска")

    # Заполненный BC должен содержать ровно четыре цифры и год не меньше 1959.
    bc_year = to_four_digit_year(row.get("manufacture_year_1"))

    if is_filled(row.get("manufacture_year_1")) and (bc_year is None or bc_year < 1959):
        add_error(errors, "Год выпуска")

    # Дата поверки: AC пустая или 31.12.1899, BD пустая -> ошибка
    if (is_empty(row.get("last_verification_date")) or is_excel_fake_date_1899(row.get("last_verification_date"))) and is_empty(row.get("last_verification_date_1")):
        add_error(errors, "Дата поверки")

    bd_date = to_date(row.get("last_verification_date_1"))

    if bd_date == date(2026, 1, 1):
        add_error(errors, "Дата поверки")

    if bd_date is not None and bc_year is not None and bd_date.year < bc_year:
        add_error(errors, "Годы несовпадают")

    # Балансовая принадлежность старого ПУ
    old_balance = norm_key(row.get("meter_ownership"))

    if (old_balance == "" or old_balance == "не задано") and is_empty(row.get("meter_ownership_1")):
        add_error(errors, "Балансовая принадлежность")

    # Активное отключение
    if is_filled(row.get("active_disconnection")):
        if RESTRICTION_ACT_TEXT not in norm_key(row.get("acts")):
            add_error(errors, "Проверка на СП")

    # Показания: проверяем только AR/AS/AT против BN/BO/BP
    for old_col, new_col, error_name in READING_RULES:
        if new_col == "t1" and bn_must_be_empty:
            continue

        old_value = to_number(row.get(old_col))
        new_value = to_number(row.get(new_col))

        if old_value is not None and new_value is not None:
            if not (old_value <= new_value):
                add_error(errors, error_name)

    # ЭЦР-2400: BN и BO должны быть равны
    if norm_key(row.get("meter_type")) == "эцр-2400":
        bn = to_number(row.get("t1"))
        bo = to_number(row.get("t2"))

        if bn is not None and bo is not None and bn != bo:
            add_error(errors, "Показания ЭЦР")

    # BR должна быть первым числом месяца, если заполнена
    br_date = to_date(row.get("meter_status_date"))

    if not br_must_be_empty and br_date is not None and br_date.day != 1:
        add_error(errors, "Дата неисправности")

    # Тип ПУ BZ: скобки, МПИ, лет — ошибка
    type_bz = row.get("meter_type_2")

    if is_filled(type_bz):
        if contains_brackets(type_bz) or contains_any(type_bz, ["мпи", "лет"]):
            add_error(errors, "Тип ПУ")

    # Модель ПУ CA: скобки НЕ ошибка, проверяем только МПИ/лет
    model_ca = row.get("meter_model_2")

    if is_filled(model_ca):
        if contains_any(model_ca, ["мпи", "лет"]):
            add_error(errors, "Модель ПУ")

    # Если BZ заполнен, CG должна быть 0
    if is_filled(row.get("meter_type_2")):
        frac = to_number(row.get("fractional_capacity_2"))

        if frac is None or frac != 0:
            add_error(errors, "Разрядность")

    # Для ИСУ разрядность целой части CF должна быть равна 6.
    if "ису" in norm_key(row.get("meter_ownership_2")):
        integer_digits = to_number(row.get("integer_capacity_2"))

        if integer_digits is None or integer_digits != 6:
            add_error(errors, "Разрядность")

    # Если BZ заполнен, CI и CJ должны быть заполнены и не "-"
    if is_filled(row.get("meter_type_2")):
        if is_dash_or_empty(row.get("rated_current_2")):
            add_error(errors, "Токи")

        if is_dash_or_empty(row.get("rated_voltage_2")):
            add_error(errors, "Напряжение")

    # Несанкционированное подключение BU
    if is_filled(row.get("unauthorized_connection")):
        add_error(errors, "Ручная проверка нарушения")

    # Допуск/установка/замена ПУ: пломбы и показания должны соответствовать результату.
    if is_pu_admission_work:
        if is_pu_admission_impossible and is_filled(row.get("seals_2")):
            add_error(errors, "ПУ допущен?")
        elif is_work_completed and is_empty(row.get("seals_2")):
            add_error(errors, "ПУ допущен?")

        if is_work_completed and is_filled(row.get("t1")):
            add_error(errors, "Не там введены показания")

    # Восстановление учета / Распломбировка ПУ
    if work_bx == "восстановление учета":
        if is_empty(row.get("seals_2")):
            add_error(errors, "Пломба")

    if work_bx == "распломбировка пу":
        if is_filled(row.get("seals_2")):
            add_error(errors, "Что с учетом?")

    # Год выпуска 2: для заданных типов старого ПУ первые две цифры AA
    # должны совпадать с последними двумя цифрами года выпуска AB.
    check_year_by_serial(errors, row.get("meter_type"), row.get("meter_serial_number"), row.get("manufacture_year"))

    # Балансовая принадлежность нового ПУ:
    # если BZ заполнено, CL должен быть из списка
    if is_filled(row.get("meter_type_2")):
        cl_value = norm_text(row.get("meter_ownership_2"))

        if cl_value not in ALLOWED_NEW_BALANCE_CL:
            add_error(errors, "Балансовая принадлежность нового ПУ")


    return errors


def _in_clause(prefix: str, values: list) -> tuple[str, dict]:
    names = ", ".join(f":{prefix}{i}" for i in range(len(values)))
    params = {f"{prefix}{i}": v for i, v in enumerate(values)}
    return names, params


async def recompute_errors(db_session: AsyncSession, task_numbers: list | None = None) -> int:
    """Пересчитывает и сохраняет ошибки в main_afl.errors (все заказчики)."""
    if task_numbers is not None and not task_numbers:
        return 0

    if task_numbers is not None:
        names, params = _in_clause("ce", task_numbers)
        result = await db_session.execute(
            text(f"SELECT * FROM main_afl WHERE task_number IN ({names})"), params)
    else:
        result = await db_session.execute(text("SELECT * FROM main_afl"))

    rows = [dict(r._mapping) for r in result]
    updates = [{"e": join_errors(check_row(row)), "tn": row["task_number"]} for row in rows]

    if updates:
        await db_session.execute(text("UPDATE main_afl SET errors = :e WHERE task_number = :tn"), updates)

    await db_session.commit()
    return len(updates)
