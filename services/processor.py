import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ─── Справочники ───

NORM_MAP = {
    "гтэс": "ГтЭС",
    "кнэс": "КнЭС",
    "нлэс": "НлЭС",
    "сэс": "СЭС",
    "тхэс": "ТхЭС",
    "тхвэс": "ТхЭС",
    "юэс": "ЮЭС",
    "вэс": "ВЭС",
}

VISIT_REASON_CODES = [
    ('00', 'Несоответствие тарифных зон'),
    ('11', 'Объект отключен'),
    ('22', 'Несоответствие номеров ПУ и ДЭС'),
    ('33', 'Отсутствует связь с ВПУ'),
    ('44', 'Установлен новый ВПУ'),
    ('55', 'Коммерческий объект'),
    ('66', 'Объект эксплуатируется'),
    ('77', 'Отсутствует тип ПУ в справочнике Алькора'),
    ('88', 'На земельном участке выявлен жилой дом'),
    ('99', 'Земельный участок не присоединён к сети'),
]


# ─── Группы признаков (словари) ───
# Повторяющиеся наборы строк вынесены в константы, чтобы не расходились между правилами.

ADMISSION_WORK_TYPES = ('Допуск ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ')
ADMISSION_WORK_TYPES_EXT = ('Допуск ПУ', 'Проверка, осмотр ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ')
ADMISSION_WORK_TYPES_IN_TASK = ('Допуск ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ')
CHECK_WORK_TYPES = ('Проверка, осмотр ПУ', 'Инструментальная проверка', 'Контроль СП', 'Контроль СП (старый)')
CONTROL_WORK_TYPES = ('Контроль СП', 'Контроль СП (старый)')
UNMETERED_WORK_TYPES = ('Инструментальная проверка', 'Проверка, осмотр ПУ', 'Перепрограммирование ПУ')
VIOLATION_WORK_TYPES = ('Проверка, осмотр ПУ', 'Перепрограммирование ПУ')
METER_STATUS_OK = ('Исправен', 'Истек МПИ')
METER_STATUS_BAD = ('Неисправен', 'Истек МПИ')
MKD_OBJECT_TYPES = ('Квартира', 'Коммунальная квартира', 'Дом блокированной застройки')
PLAN_INDOOR_PLACES = ('в квартире', 'в доме', 'закрытый тамбур', 'квартира')
RESULT_OUTPUTS = ('Показания', 'Проверка', 'Нарушение')
DOMESTIC_PLACES = (
    'в доме', 'в квартире', 'комната', 'В ДОМЕ', 'в жилом доме',
    'щит /щитовая/   в доме', 'на фасаде', 'в летнем доме', 'в сарае', 'в бане', 'сарай', 'хозблок',
    'В ЩУ', 'в гараже', 'на фасаде строящегося дома', 'тп', 'в ЩРН кладовой', 'фасад', 'в комнате',
    'в  доме', 'баня', 'жилой дом', 'бытовка', 'В квартире', 'в тп', 'коридор /прихожая/ жилого дома',
    'в быт.помещении', 'гараж/сарай', 'на веранде', 'на кухне', 'ГРЩ', 'ТП', 'в ТП',
)


# ─── Хелперы для сборки SQL ───

def _sql_list(values) -> str:
    """Список литералов для IN (...): 'a', 'b', 'c'."""
    return ", ".join(f"'{v}'" for v in values)


def _in(column: str, values) -> str:
    return f"{column} IN ({_sql_list(values)})"


def _not_in(column: str, values) -> str:
    return f"{column} NOT IN ({_sql_list(values)})"


def regexp(expr, item):
    """Функция REGEXP для SQLite"""
    if item is None:
        return False
    try:
        return re.search(expr, item) is not None
    except:
        return False


def process_row(text):
    """Извлекает norm_name и reg_number из visit_reason"""
    if not text or not isinstance(text, str):
        return "-", "б/н"
    for raw_key, norm_name in NORM_MAP.items():
        pattern = re.compile(re.escape(raw_key), re.IGNORECASE)
        match = pattern.search(text)
        if match:
            found_raw = match.group(0)
            pos = match.end()
            if pos < len(text) and text[pos] == '/':
                remaining = text[pos + 1:]
                number_match = re.match(r'([^/\s,.;:()]+/\d+)', remaining)
                if number_match:
                    full_number = f"{found_raw}/{number_match.group(1)}"
                    return norm_name, full_number
            return norm_name, "б/н"
    return "-", "б/н"


# ─── Правила Шага 4: task_output / task_detail (порядок = приоритет) ───
# Каждое правило — (SET-часть, WHERE-часть, progress). progress пишется в upload_progress ПОСЛЕ правила.

TASK_OUTPUT_RULES = [
    ("task_output = 'В работе', task_detail = 'Статус не закрыто/завершено'",
     "status NOT LIKE 'З%'", None),
    ("task_output = 'Не исполнено', task_detail = 'Нет даты окончания выполнения работы'",
     "work_end_date IS NULL AND task_output IS NULL", None),
    ("task_output = 'Невозможно', task_detail = '0'",
     "meter_inspection_results = 'Невозможно выполнить осмотр/проверку ПУ' AND task_output IS NULL", None),
    ("task_output = 'Контроль', task_detail = '1'",
     f"{_in('work_type_in_task', CONTROL_WORK_TYPES)} AND work_result = 'Работа выполнена'", 40),

    # Допуск 2 / 3
    ("task_output = 'Допуск', task_detail = '2'",
     f"{_in('work_type_in_task', ADMISSION_WORK_TYPES_EXT)} AND {_in('work_type', ADMISSION_WORK_TYPES)} AND t1_1 <> '-' AND task_output IS NULL", None),
    ("task_output = 'Допуск', task_detail = '3'",
     f"{_in('work_type_in_task', ADMISSION_WORK_TYPES_EXT)} AND {_in('work_type', ADMISSION_WORK_TYPES)} AND t1_1 = '-' AND violations = 'Да' AND task_output IS NULL", None),

    # Не исполнено — процедура допуска 1 / 2
    ("task_output = 'Не исполнено', task_detail = 'Несоблюдение процедуры допуска 1'",
     f"{_in('work_type_in_task', ADMISSION_WORK_TYPES_IN_TASK)} AND t1_1 = '-' AND violations = 'Нет' AND task_output IS NULL", None),
    ("task_output = 'Не исполнено', task_detail = 'Несоблюдение процедуры допуска 2'",
     f"work_type_in_task = 'Проверка, осмотр ПУ' AND {_in('work_type', ADMISSION_WORK_TYPES)} AND t1_1 = '-' AND violations = 'Нет' AND task_output IS NULL", None),

    ("task_output = 'Допуск', task_detail = '4'",
     f"{_in('work_type_in_task', ADMISSION_WORK_TYPES_IN_TASK)} AND sent_to_billing = 'Да' AND task_output = 'Не исполнено'", 50),

    ("task_output = 'Проверка', task_detail = '11'",
     f"{_in('work_type', ADMISSION_WORK_TYPES)} AND violations = 'Да' AND task_output IS NULL", None),
    ("task_output = 'Нарушение'",
     "violations = 'Да' AND task_detail IS NULL", None),
    ("task_detail = 'Акт неучтённого потребления'",
     "task_output = 'Нарушение' AND (meter_malfunction IS NOT NULL OR unauthorized_connection IS NOT NULL OR unauthorized_interference IS NOT NULL) "
     f"AND meter_status = 'Исправен' AND {_in('meter_installation_place', DOMESTIC_PLACES)} AND task_detail IS NULL", None),
    ("task_detail = 'Выявлено нарушение учёта'",
     "task_output = 'Нарушение' AND task_detail IS NULL", None),

    # «Проверка 12» (task_output='Нарушение' + customer='ПСК') — намеренно отключена.

    ("task_output = 'Показания', task_detail = '13'",
     "work_type_in_task = 'Перепрограммирование ПУ' AND meter_status = 'Исправен' AND violations = 'Нет' AND (t1 <> '-' OR t1_1 <> '-') AND task_output IS NULL", None),
    ("task_output = 'Показания', task_detail = '5'",
     f"{_in('meter_status', METER_STATUS_OK)} AND t1 <> '-' AND violations = 'Нет' AND task_output IS NULL", None),
    ("task_output = 'Показания', task_detail = 'Восстановление учета'",
     "meter_status = 'Неисправен' AND final_meter_status = 'Исправен' AND t1 <> '-' AND violations = 'Нет' AND work_type = 'Восстановление учета' AND task_output IS NULL", 60),

    ("task_output = 'Не исполнено', task_detail = 'ПУ исправен, показания не зафиксированы'",
     "meter_status = 'Исправен' AND work_type = 'Проверка, осмотр ПУ' AND t1 = '-' AND task_output IS NULL", None),
    ("task_output = 'Не исполнено', task_detail = 'Не подтверждено отсутствие учёта, не указано наличие учёта'",
     "work_type_in_task = 'Проверка, осмотр ПУ' AND meter_status = 'Неисправен' AND violations = 'Нет' AND work_type = 'Проверка, осмотр ПУ' AND task_output IS NULL", None),

    ("task_output = 'Проверка', task_detail = '6'",
     "meter_status IS NULL AND work_result = 'Работа выполнена' AND task_output IS NULL", None),
    ("task_output = 'Проверка', task_detail = '7'",
     f"{_in('meter_status', METER_STATUS_BAD)} AND violations = 'Да' AND task_output IS NULL", None),
    ("task_output = 'Проверка', task_detail = '8'",
     "sent_to_billing = 'Да' AND task_output IS NULL", None),
    ("task_output = 'Не исполнено', task_detail = '9'",
     "task_output IS NULL", None),
    ("task_output = 'Проверка', task_detail = '10'",
     "sent_to_billing = 'Да' AND task_output = 'Не исполнено'", 70),
]


# ─── Проверки по comment (REGEXP) ───

COMMENT_RULES = [
    ("task_output = 'Проверка', task_detail = 'Объект не эксплуатируется'",
     "work_type_in_task = 'Проверка, осмотр ПУ' AND task_output = 'Невозможно' AND unsuccessful_inspection_reason = 'Расселенная квартира'", None),
    ("task_output = 'Проверка', task_detail = 'Объект отсутствует'",
     "work_type_in_task = 'Проверка, осмотр ПУ' AND task_output = 'Невозможно' AND unsuccessful_inspection_reason = 'Здание снесено'", None),
    ("task_output = 'Проверка', task_detail = 'Несоответствие тарифных зон'",
     f"{_in('work_type_in_task', CHECK_WORK_TYPES)} AND comment REGEXP '(^|[^0-9])00([^0-9]|$)'", None),
]

# Коды 11–99 (все, кроме 00) для «Проверка, осмотр ПУ».
for _code, _desc in VISIT_REASON_CODES[1:]:
    COMMENT_RULES.append(
        (f"task_output = 'Проверка', task_detail = '{_desc}'",
         f"work_type_in_task = 'Проверка, осмотр ПУ' AND comment REGEXP '(^|[^0-9]){_code}([^0-9]|$)'", None)
    )

COMMENT_RULES += [
    ("task_output = 'Проверка', task_detail = 'Несоответствие разрядности'",
     f"{_in('work_type_in_task', CHECK_WORK_TYPES)} AND comment REGEXP '(^| )!!( |$)'", None),
    ("task_output = 'Проверка', task_detail = 'Неподключенный новый ввод'",
     r"work_type_in_task = 'Проверка, осмотр ПУ' AND comment REGEXP '(^| )\?\?( |$)'", None),
    ("task_output = 'Допуск', task_detail = 'Отсутствует тип ПУ в справочнике Алькора'",
     f"{_in('work_type_in_task', ADMISSION_WORK_TYPES_EXT)} AND comment REGEXP '(^|[^0-9])77([^0-9]|$)'", None),
    ("task_output = 'Невозможно', task_detail = 'Причина невыполнения: Нет доступа до ПУ'",
     "work_type_in_task = 'Проверка, осмотр ПУ' AND unsuccessful_inspection_reason = 'Нет доступа до ПУ'", None),
    ("task_output = 'Невозможно', task_detail = 'Причина невыполнения: Помещение не найдено'",
     "work_type_in_task = 'Проверка, осмотр ПУ' AND unsuccessful_inspection_reason = 'Помещение не найдено'", 75),
]


# ─── Правила Шага 5: task_report (вид работ) ───

TASK_REPORT_RULES = [
    ("task_report = 'Периодический контроль БП'",
     "task_output = 'Контроль' AND task_report IS NULL", None),
    ("task_report = 'Допуск ПУ в ИЖС'",
     f"task_output = 'Допуск' AND {_not_in('service_object_type', MKD_OBJECT_TYPES)} AND task_report IS NULL", None),
    ("task_report = 'Допуск ПУ в МКД'",
     f"task_output = 'Допуск' AND {_in('service_object_type', MKD_OBJECT_TYPES)} AND task_report IS NULL", None),
    ("task_report = 'Выявление безучетного потребления БП'",
     f"{_in('work_type_in_task', UNMETERED_WORK_TYPES)} AND task_detail = 'Акт неучтённого потребления' AND task_type = 'Внеплановый' AND task_report IS NULL", None),
    ("task_report = 'Бытовые заявки'",
     "task_report = 'Выявление безучетного потребления БП' AND task_number LIKE 'ОФТП%'", None),
    ("task_report = 'Инструментальная проверка'",
     "work_type_in_task = 'Инструментальная проверка' AND task_output = 'Показания' AND task_report IS NULL", None),
    ("task_report = 'Инструментальная проверка'",
     "work_type_in_task = 'Инструментальная проверка' AND task_detail = 'Выявлено нарушение учёта' AND task_type = 'Внеплановый' AND task_report IS NULL", None),
    ("task_report = 'Бытовые заявки'",
     f"{_in('work_type_in_task', VIOLATION_WORK_TYPES)} AND task_detail = 'Выявлено нарушение учёта' AND task_type = 'Внеплановый' AND task_report IS NULL", None),
    ("task_report = 'Бытовые заявки'",
     "task_output = 'Показания' AND work_type_in_task = 'Перепрограммирование ПУ' AND task_report IS NULL", 80),

    ("task_report = 'План ИЖС'",
     f"work_type_in_task = 'Проверка, осмотр ПУ' AND {_in('task_output', RESULT_OUTPUTS)} AND task_type = 'Плановый' AND {_not_in('service_object_type', MKD_OBJECT_TYPES)} AND task_report IS NULL", None),
    ("task_report = 'План лестница'",
     f"work_type_in_task = 'Проверка, осмотр ПУ' AND {_in('task_output', RESULT_OUTPUTS)} AND task_type = 'Плановый' AND {_in('service_object_type', MKD_OBJECT_TYPES)} AND {_not_in('meter_installation_place', PLAN_INDOOR_PLACES)} AND task_report IS NULL", None),
    ("task_report = 'План лестница'",
     f"work_type_in_task = 'Проверка, осмотр ПУ' AND {_in('task_output', RESULT_OUTPUTS)} AND task_type = 'Плановый' AND {_in('service_object_type', MKD_OBJECT_TYPES)} AND meter_installation_place IS NULL AND task_report IS NULL", None),
    ("task_report = 'План квартира'",
     f"work_type_in_task = 'Проверка, осмотр ПУ' AND {_in('task_output', RESULT_OUTPUTS)} AND task_type = 'Плановый' AND {_in('service_object_type', MKD_OBJECT_TYPES)} AND {_in('meter_installation_place', PLAN_INDOOR_PLACES)} AND task_report IS NULL", None),
    ("task_report = 'Бытовые заявки'",
     f"work_type_in_task = 'Проверка, осмотр ПУ' AND {_in('task_output', RESULT_OUTPUTS)} AND task_type = 'Внеплановый' AND task_report IS NULL", None),
    ("task_report = 'Ручная проверка'",
     f"{_in('work_type', ADMISSION_WORK_TYPES)} AND task_report IS NULL", 82),
]


async def _apply_rules(db_session, rules, upload_progress, upload_id, total_rows) -> None:
    """Последовательно выполняет правила классификации (UPDATE raw_afl)."""
    for set_clause, where, progress in rules:
        await db_session.execute(text(f"UPDATE raw_afl SET {set_clause} WHERE {where}"))
        if progress is not None:
            upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}


async def process_raw_afl(db_session: AsyncSession, upload_progress: dict, upload_id: str, total_rows: int) -> bool:
    try:
        # === Регистрируем REGEXP ===
        await db_session.execute(text("SELECT 1"))  # убеждаемся что сессия жива
        def setup_regexp(connection):
            connection.connection.create_function("REGEXP", 2, regexp)

        from data.config import engine as async_engine
        async with async_engine.begin() as conn:
            await conn.run_sync(setup_regexp)

        await db_session.execute(
            text("DELETE FROM raw_afl WHERE executor_organization NOT IN (SELECT DISTINCT dept FROM users)")
        )
        await db_session.execute(
            text("DELETE FROM raw_afl WHERE task_number is null")
        )
        await db_session.execute(text(
            "UPDATE raw_afl SET executor = 'Загуменнова Алёна Юрьевна' WHERE executor = 'Жагорова Алёна Юрьевна'"
        ))
        await db_session.execute(text(
            "UPDATE raw_afl SET executor = 'Петрова Юлия Сергеевна' WHERE executor = 'Петрова Юлия Сергеевна (ПЭК)'"
        ))

        # === Шаг 1: region из municipal_district ===
        await db_session.execute(text(
            "UPDATE raw_afl SET region = rtrim(SUBSTR(municipal_district, 1, 3))"
        ))
        progress = 25
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}

        # === Шаг 2: grid из visit_reason (Python-обработка) ===
        result = await db_session.execute(text("SELECT id, visit_reason FROM raw_afl"))
        rows = result.fetchall()
        updates = [
            {"grid": process_row(visit_text)[0], "id": row_id}
            for row_id, visit_text in rows
        ]
        if updates:
            await db_session.execute(
                text("UPDATE raw_afl SET grid = :grid WHERE id = :id"),
                updates,
            )

        progress = 30
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}

        # === Шаг 3: customer (A) ===
        await db_session.execute(text(
            "UPDATE raw_afl SET customer = CASE WHEN grid = '-' THEN 'ПСК' ELSE 'РЛЭ' END"
        ))
        progress = 35
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}

        # === Шаг 4: task_output (DI) и task_detail (DK) ===
        await _apply_rules(db_session, TASK_OUTPUT_RULES, upload_progress, upload_id, total_rows)

        # === Проверки по comment (CS) через REGEXP ===
        await _apply_rules(db_session, COMMENT_RULES, upload_progress, upload_id, total_rows)

        # === Шаг 5: task_report (DJ) ===
        await _apply_rules(db_session, TASK_REPORT_RULES, upload_progress, upload_id, total_rows)


        # === Шаг 6: task_report_id ===
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report_id = "
            "SUBSTR(work_end_date, 7, 4) || '-' || SUBSTR(work_end_date, 4, 2) || '-' || "
            "SUBSTR(work_end_date, 1, 2) || '-' || metering_point "
            "WHERE task_report IS NOT NULL AND task_report <> 'Ручная проверка'"
        ))

        # Форматирование created_at
        await db_session.execute(text(
            "UPDATE raw_afl SET created_at = "
            "SUBSTR(created_at, 7, 4) || '-' || SUBSTR(created_at, 4, 2) || '-' || SUBSTR(created_at, 1, 2)"
        ))

        # Дедубликация: оставляем самую новую строку (по work_start_date) для каждого task_report_id.
        await db_session.execute(text("""
            UPDATE raw_afl SET task_report = 'Дубли', task_detail = 'Дубли'
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                        ROW_NUMBER() OVER (PARTITION BY task_report_id ORDER BY work_start_date DESC, id DESC) AS rn
                    FROM raw_afl
                    WHERE task_report_id IS NOT NULL
                )
                WHERE rn > 1
            )
        """))

        progress = 85
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}

        # === Недопуск ===
        await db_session.execute(text(
            "UPDATE raw_afl SET task_detail = 'Недопуск ПУ' "
            "WHERE task_output = 'Допуск' AND (meter_malfunction IS NOT NULL OR unauthorized_interference IS NOT NULL "
            "OR unauthorized_connection IS NOT NULL OR additional_violations IS NOT NULL)"
        ))

        # === Не исполнено 14 ===
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Не исполнено', task_report = NULL, task_detail = '14' "
            "WHERE meter_type IS NULL AND meter_type_2 IS NULL AND task_report = 'Выявление безучетного потребления БП'"
        ))
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Бытовые заявки' "
            "WHERE task_report = 'Выявление безучетного потребления БП' AND customer = 'ПСК'"
        ))

        # === Шаг 7: done_day из work_end_date ===
        await db_session.execute(text(
            "UPDATE raw_afl SET done_day = "
            "SUBSTR(work_end_date, 7, 4) || '-' || SUBSTR(work_end_date, 4, 2) || '-' || SUBSTR(work_end_date, 1, 2)"
        ))
        await db_session.execute(text(
            "UPDATE raw_afl SET done_day_type = (SELECT type FROM calendar WHERE calendar.d = raw_afl.done_day)"
        ))

        await db_session.commit()

        upload_progress[upload_id] = {"status": "processing", "progress": 90, "total": total_rows}
        return True

    except Exception as e:
        await db_session.rollback()
        upload_progress[upload_id] = {
            "status": "error",
            "progress": 0,
            "total": total_rows,
            "message": f"Ошибка обработки: {str(e)}"
        }
        raise




