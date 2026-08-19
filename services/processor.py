import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#   АКТУАЛЬНО НА 06/07 >> 10/07 >> 16/07 >> 21/07

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


async def process_raw_afl(db_session: AsyncSession, upload_progress: dict, upload_id: str, total_rows: int) -> bool:
    try:
        # === Регистрируем REGEXP ===
        # Используем сырой sync_engine через run_sync
        await db_session.execute(text("SELECT 1"))  # убеждаемся что сессия жива
        # Регистрируем функцию через sync connection
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

        progress = 20
        
        # === Шаг 1: region из municipal_district ===
        await db_session.execute(text(
            "UPDATE raw_afl SET region = rtrim(SUBSTR(municipal_district, 1, 3))"
        ))
        
        progress = 25
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}
        
        # === Шаг 2: grid из visit_reason (Python-обработка) ===
        result = await db_session.execute(text("SELECT id, visit_reason FROM raw_afl"))
        rows = result.fetchall()

        # Один executemany вместо N+1 отдельных UPDATE (раньше — по запросу на строку).
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
        
        # === Шаг 4: task_output (DI) и task_detail (DK) — базовые ===
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'В работе', task_detail = 'Статус не закрыто/завершено' "
            "WHERE status NOT LIKE 'З%'"
        ))
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Не исполнено', task_detail = 'Нет даты окончания выполнения работы' "
            "WHERE work_end_date IS NULL AND task_output IS NULL"
        ))
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Невозможно', task_detail = '0' "
            "WHERE meter_inspection_results = 'Невозможно выполнить осмотр/проверку ПУ' AND task_output IS NULL"
        ))
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Контроль', task_detail = '1' "
            "WHERE work_type_in_task IN ('Контроль СП', 'Контроль СП (старый)') AND work_result = 'Работа выполнена'"
        ))
        
        progress = 40
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}
        
        # === Допуск 2 ===
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Допуск', task_detail = '2' "
            "WHERE work_type_in_task IN ('Допуск ПУ', 'Проверка, осмотр ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ') "
            "AND work_type IN ('Допуск ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ') "
            "AND t1_1 <> '-' AND task_output IS NULL"
        ))
        
        # Допуск 3
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Допуск', task_detail = '3' "
            "WHERE work_type_in_task IN ('Допуск ПУ', 'Проверка, осмотр ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ') "
            "AND work_type IN ('Допуск ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ') "
            "AND t1_1 = '-' AND violations = 'Да' AND task_output IS NULL"
        ))
        
        # Не исполнено — процедура допуска 1
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Не исполнено', task_detail = 'Несоблюдение процедуры допуска 1' "
            "WHERE work_type_in_task IN ('Допуск ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ') "
            "AND t1_1 = '-' AND violations = 'Нет' AND task_output IS NULL"
        ))
        
        # Не исполнено — процедура допуска 2
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Не исполнено', task_detail = 'Несоблюдение процедуры допуска 2' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' "
            "AND work_type IN ('Допуск ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ') "
            "AND t1_1 = '-' AND violations = 'Нет' AND task_output IS NULL"
        ))
        
        # Допуск 4
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Допуск', task_detail = '4' "
            "WHERE work_type_in_task IN ('Допуск ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ') "
            "AND sent_to_billing = 'Да' AND task_output = 'Не исполнено'"
        ))
        
        progress = 50
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}
        
        # === Проверка 11 ===
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Проверка', task_detail = '11' "
            "WHERE work_type IN ('Допуск ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ') "
            "AND violations = 'Да' AND task_output IS NULL"
        ))
        
        # Нарушение
        await db_session.execute(text("UPDATE raw_afl SET task_output = 'Нарушение' WHERE violations = 'Да' AND task_detail IS NULL"))

        await db_session.execute(text(
            "UPDATE raw_afl SET task_detail = 'Акт неучтённого потребления' WHERE task_output = 'Нарушение' "
            "AND (meter_malfunction IS NOT NULL OR unauthorized_connection IS NOT NULL OR unauthorized_interference IS NOT NULL) "
            "AND meter_status = 'Исправен' AND meter_installation_place in ('в доме', 'в квартире', 'комната', 'В ДОМЕ', 'в жилом доме', "
            "'щит /щитовая/   в доме', 'на фасаде', 'в летнем доме', 'в сарае', 'в бане', 'сарай', 'хозблок', "
            "'В ЩУ', 'в гараже', 'на фасаде строящегося дома', 'тп', 'в ЩРН кладовой', 'фасад', 'в комнате', "
            "'в  доме', 'баня', 'жилой дом', 'бытовка', 'В квартире', 'в тп', 'коридор /прихожая/ жилого дома', "
            "'в быт.помещении', 'гараж/сарай', 'на веранде', 'на кухне', 'ГРЩ', 'ТП', 'в ТП') AND task_detail IS NULL"
        )) # acts like '%несанкционированного%'

        await db_session.execute(text(
            "UPDATE raw_afl SET task_detail = 'Выявлено нарушение учёта' WHERE task_output = 'Нарушение'  "
            "AND task_detail IS NULL"
        ))

        # Проверка 12
        # await db_session.execute(text(
        #     "UPDATE raw_afl SET task_output = 'Проверка', task_detail = '12' "
        #     "WHERE task_output = 'Нарушение' AND customer = 'ПСК'"
        # ))
        
        # Показания 13
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Показания', task_detail = '13' "
            "WHERE work_type_in_task = 'Перепрограммирование ПУ' AND meter_status = 'Исправен' "
            "AND violations = 'Нет' AND (t1 <> '-' OR t1_1 <> '-') AND task_output IS NULL"
        ))
        
        # Показания 5
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Показания', task_detail = '5' "
            "WHERE meter_status in ('Истек МПИ', 'Исправен') AND t1 <> '-' AND violations = 'Нет' AND task_output IS NULL"
        ))

        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Показания', task_detail = 'Восстановление учета' WHERE meter_status = 'Неисправен' "
            "AND final_meter_status = 'Исправен' AND t1 <> '-' AND violations = 'Нет' AND work_type = 'Восстановление учета' AND task_output IS NULL"
        ))

        progress = 60
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}
        
        # Не исполнено — ПУ исправен, показания не зафиксированы
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Не исполнено', task_detail = 'ПУ исправен, показания не зафиксированы' "
            "WHERE meter_status = 'Исправен' AND work_type = 'Проверка, осмотр ПУ' "
            "AND t1 = '-' AND task_output IS NULL"
        ))
        
        # Не исполнено — не подтверждено отсутствие учёта
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Не исполнено', "
            "task_detail = 'Не подтверждено отсутствие учёта, не указано наличие учёта' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' AND meter_status = 'Неисправен' "
            "AND violations = 'Нет' AND work_type = 'Проверка, осмотр ПУ' AND task_output IS NULL"
        ))
        
        # Проверка 6
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Проверка', task_detail = '6' "
            "WHERE meter_status IS NULL AND work_result = 'Работа выполнена' AND task_output IS NULL"
        ))
        
        # Проверка 7
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Проверка', task_detail = '7' "
            "WHERE meter_status IN ('Неисправен', 'Истек МПИ') AND violations = 'Да' AND task_output IS NULL"
        ))
        
        # Проверка 8
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Проверка', task_detail = '8' "
            "WHERE sent_to_billing = 'Да' AND task_output IS NULL"
        ))
        
        # Не исполнено 9
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Не исполнено', task_detail = '9' "
            "WHERE task_output IS NULL"
        ))
        
        # Проверка 10
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Проверка', task_detail = '10' "
            "WHERE sent_to_billing = 'Да' AND task_output = 'Не исполнено'"
        ))
        
        progress = 70
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}
        
        # === Проверки по comment (CS) через REGEXP ===
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Проверка', task_detail = 'Объект не эксплуатируется' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' AND task_output = 'Невозможно' "
            "AND unsuccessful_inspection_reason = 'Расселенная квартира'"
        ))
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Проверка', task_detail = 'Объект отсутствует' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' AND task_output = 'Невозможно' "
            "AND unsuccessful_inspection_reason = 'Здание снесено'"
        ))
        
        # Несоответствие тарифных зон (00)
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Проверка', task_detail = 'Несоответствие тарифных зон' "
            "WHERE work_type_in_task IN ('Проверка, осмотр ПУ', 'Инструментальная проверка', 'Контроль СП', 'Контроль СП (старый)') "
            "AND comment REGEXP '(^|[^0-9])00([^0-9]|$)'"
        ))
        
        # Коды 11-99 для Проверка, осмотр ПУ
        for code, desc in VISIT_REASON_CODES[1:]:
            await db_session.execute(text(
                f"UPDATE raw_afl SET task_output = 'Проверка', task_detail = '{desc}' "
                f"WHERE work_type_in_task = 'Проверка, осмотр ПУ' "
                f"AND comment REGEXP '(^|[^0-9]){code}([^0-9]|$)'"
            ))
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Проверка', task_detail = 'Несоответствие разрядности' "
            "WHERE work_type_in_task IN ('Проверка, осмотр ПУ', 'Инструментальная проверка', 'Контроль СП', 'Контроль СП (старый)') "
            "AND comment REGEXP '(^| )!!( |$)'"
        ))

        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Проверка', task_detail = 'Неподключенный новый ввод' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' "
            "AND comment REGEXP '(^| )\\?\\?( |$)'"
        ))

        # 77 для Допуск
        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Допуск', task_detail = 'Отсутствует тип ПУ в справочнике Алькора' "
            "WHERE work_type_in_task IN ('Допуск ПУ', 'Проверка, осмотр ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ') "
            "AND comment REGEXP '(^|[^0-9])77([^0-9]|$)'"
        ))

        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Невозможно', task_detail = 'Причина невыполнения: Нет доступа до ПУ' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' AND unsuccessful_inspection_reason = 'Нет доступа до ПУ'"
        ))

        await db_session.execute(text(
            "UPDATE raw_afl SET task_output = 'Невозможно', task_detail = 'Причина невыполнения: Помещение не найдено' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' AND unsuccessful_inspection_reason = 'Помещение не найдено'"
        ))

        progress = 75
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}
        
        # === Шаг 5: task_report (DJ) ===
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Периодический контроль БП' "
            "WHERE task_output = 'Контроль' AND task_report IS NULL"
        ))
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Допуск ПУ в ИЖС' "
            "WHERE task_output = 'Допуск' AND service_object_type NOT IN "
            "('Квартира', 'Коммунальная квартира', 'Дом блокированной застройки') AND task_report IS NULL"
        ))
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Допуск ПУ в МКД' "
            "WHERE task_output = 'Допуск' AND service_object_type IN "
            "('Квартира', 'Коммунальная квартира', 'Дом блокированной застройки') AND task_report IS NULL"
        ))
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Выявление безучетного потребления БП' "
            "WHERE work_type_in_task in ('Инструментальная проверка', 'Проверка, осмотр ПУ', 'Перепрограммирование ПУ') AND task_detail = 'Акт неучтённого потребления' "
            "AND task_type = 'Внеплановый' AND task_report IS NULL"
        ))

        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Бытовые заявки' "
            "WHERE task_report = 'Выявление безучетного потребления БП' AND task_number LIKE 'ОФТП%'"
        ))

        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Инструментальная проверка' "
            "WHERE work_type_in_task = 'Инструментальная проверка' AND task_output = 'Показания' "
            "AND task_report IS NULL"
        ))
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Инструментальная проверка' "
            "WHERE work_type_in_task = 'Инструментальная проверка' AND task_detail = 'Выявлено нарушение учёта' "
            "AND task_type = 'Внеплановый' AND task_report IS NULL"
        ))
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Бытовые заявки' "
            "WHERE work_type_in_task in ('Проверка, осмотр ПУ', 'Перепрограммирование ПУ') AND task_detail = 'Выявлено нарушение учёта' "
            "AND task_type = 'Внеплановый' AND task_report IS NULL"
        ))
        
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Бытовые заявки' "
            "WHERE task_output = 'Показания' AND work_type_in_task = 'Перепрограммирование ПУ' "
            "AND task_report IS NULL"
        ))
        
        progress = 80
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}
        
        # План ИЖС
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'План ИЖС' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' AND task_output IN ('Показания', 'Проверка', 'Нарушение') "
            "AND task_type = 'Плановый' AND service_object_type NOT IN "
            "('Квартира', 'Коммунальная квартира', 'Дом блокированной застройки') AND task_report IS NULL"
        ))
        
        # План лестница (1)
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'План лестница' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' AND task_output IN ('Показания', 'Проверка', 'Нарушение') "
            "AND task_type = 'Плановый' AND service_object_type IN "
            "('Квартира', 'Коммунальная квартира', 'Дом блокированной застройки') "
            "AND meter_installation_place NOT IN ('в квартире', 'в доме', 'закрытый тамбур', 'квартира') "
            "AND task_report IS NULL"
        ))
        
        # План лестница (2)
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'План лестница' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' AND task_output IN ('Показания', 'Проверка', 'Нарушение') "
            "AND task_type = 'Плановый' AND service_object_type IN "
            "('Квартира', 'Коммунальная квартира', 'Дом блокированной застройки') "
            "AND meter_installation_place IS NULL AND task_report IS NULL"
        ))
        
        # План квартира
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'План квартира' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' AND task_output IN ('Показания', 'Проверка', 'Нарушение') "
            "AND task_type = 'Плановый' AND service_object_type IN "
            "('Квартира', 'Коммунальная квартира', 'Дом блокированной застройки') "
            "AND meter_installation_place IN ('в квартире', 'в доме', 'закрытый тамбур', 'квартира') "
            "AND task_report IS NULL"
        ))

        # Бытовые заявки (Внеплановый)
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Бытовые заявки' "
            "WHERE work_type_in_task = 'Проверка, осмотр ПУ' AND task_output IN ('Показания', 'Проверка', 'Нарушение') "
            "AND task_type = 'Внеплановый' AND task_report IS NULL"
        ))
        
        # Ручная проверка
        await db_session.execute(text(
            "UPDATE raw_afl SET task_report = 'Ручная проверка' "
            "WHERE work_type IN ('Допуск ПУ', 'Замена/Установка ПУ', 'Установка / замена ПУ') "
            "AND task_report IS NULL"
        ))
        
        progress = 82
        upload_progress[upload_id] = {"status": "processing", "progress": progress, "total": total_rows}
        
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
        
        # Дедубликация: оставляем самую новую строку (по work_start_date) для каждого task_report_id,
        # остальным ставим task_report = 'Дубли', task_detail = 'Дубли'
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