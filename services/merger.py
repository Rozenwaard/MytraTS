from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sql import build_in_clause
from services.premium import apply_norms


def _sortable_date(value) -> str:
    """'DD.MM.YYYY HH:MM:SS' → 'YYYY-MM-DD HH:MM:SS' (для корректного сравнения дат)."""
    if not value:
        return ""
    s = str(value).strip()
    parts = s.split(" ", 1)
    d = parts[0].split(".")
    if len(d) == 3:
        return f"{d[2]}-{d[1]}-{d[0]}" + (f" {parts[1]}" if len(parts) > 1 else "")
    return s


def _dup_key(c) -> tuple:
    """Ключ победителя дедупликации: новее work_start_date → существующая → больший seq."""
    return (_sortable_date(c.get("work_start_date")), 0 if c["is_incoming"] else 1, c.get("seq", 0))


MAIN_AFL_COLUMNS = [
    'task_number', 'task_source', 'task_type', 'work_type_in_task',
    'created_at', 'address', 'municipal_district', 'house_type',
    'personal_account', 'contract_status', 'contract_created_at',
    'debt_amount', 'debt_calculation_date',
    'disconnection_reconnection_debt_amount', 'debt_calculation_date_1',
    'notification_debt_amount', 'debt_calculation_date_2', 'due_date',
    'service_object_type', 'subscriber_name', 'subscriber_type',
    'subscriber_phone', 'metering_point', 'meter_type', 'meter_model',
    'meter_serial_number', 'manufacture_year', 'last_verification_date',
    'meter_tariff_rate', 'integer_capacity', 'fractional_capacity',
    'calibration_interval', 'rated_current', 'rated_voltage',
    'meter_installation_place', 'meter_status', 'meter_ownership',
    'active_disconnection', 'last_readings_t1_estimated',
    'last_readings_t2_estimated', 'last_readings_t3_estimated',
    'last_estimated_readings_date', 'last_readings_t1_control',
    'last_readings_t2_control', 'last_readings_t3_control',
    'last_control_readings_date', 'seals', 'has_current_transformer',
    'has_voltage_transformer', 'meter_inspection_results',
    'meter_type_1', 'meter_model_1', 'meter_serial_number_1',
    'manufacture_year_1', 'last_verification_date_1', 'meter_tariff_rate_1',
    'integer_capacity_1', 'fractional_capacity_1', 'calibration_interval_1',
    'rated_current_1', 'rated_voltage_1', 'meter_installation_place_1',
    'meter_ownership_1', 'seals_1', 't1', 't2', 't3', 'violations',
    'meter_status_date', 'meter_malfunction', 'unauthorized_interference',
    'unauthorized_connection', 'additional_violations',
    'unsuccessful_inspection_reason', 'work_type', 'work_result',
    'meter_type_2', 'meter_model_2', 'meter_serial_number_2',
    'manufacture_year_2', 'last_verification_date_2', 'meter_tariff_rate_2',
    'integer_capacity_2', 'fractional_capacity_2', 'calibration_interval_2',
    'rated_current_2', 'rated_voltage_2', 'meter_installation_place_2',
    'meter_ownership_2', 'seals_2', 't1_1', 't2_1', 't3_1',
    'final_meter_status', 'acts', 'comment', 'work_start_date',
    'work_end_date', 'sent_to_billing', 'billing_sent_at',
    'task_organization', 'third_party_organization', 'assignee',
    'executor', 'executor_organization', 'visit_reason', 'verified',
    'status', 'work_result_1', 'status_changed_at', 'task_link',
    'customer', 'task_output', 'task_report', 'task_detail',
    'region', 'grid', 'task_report_id', 'done_day', 'done_day_type',
]


# «Жизненные» поля, которые обновляются даже у строк с номером реестра:
# проверка/статус/биллинг меняются в источнике независимо от реестра.
STATUS_ONLY_COLUMNS = [
    'verified', 'status', 'sent_to_billing', 'billing_sent_at', 'status_changed_at',
]


async def merge_to_main(db_session, upload_progress, upload_id, total_rows):
    # Существующие строки: task_number → (текущий reestr_number, task_detail).
    # Плюс активные строки по task_report_id — кандидаты дедупликации (учитывает серию загрузок).
    result = await db_session.execute(text(
        "SELECT task_number, reestr_number, task_detail, task_report_id, work_start_date, task_report FROM main_afl"
    ))
    existing = {}
    active_by_report = {}
    for row in result:
        tn, rn, td, tri, wsd, tr = row
        existing[tn] = (rn, td)
        if tri and tr != "Дубли" and td != "Разногласия":
            active_by_report.setdefault(tri, []).append(
                {"task_number": tn, "reestr_number": rn, "work_start_date": wsd}
            )

    columns_str = ', '.join(f'"{c}"' for c in MAIN_AFL_COLUMNS)
    result = await db_session.execute(text(
        f"SELECT {columns_str} FROM raw_afl "
        "WHERE status IS NOT NULL "
        "AND task_number IS NOT NULL"
    ))
    all_rows = [dict(row._mapping) for row in result]

    new_rows = [row for row in all_rows if row['task_number'] not in existing]

    # Перезаписываем только строки без номера реестра (пусто или 'Отклонён')
    # и без пометки 'Разногласия'. Защищены от перезаписи: строки с реальным
    # номером реестра и строки с task_detail = 'Разногласия'.
    update_rows = []
    reset_reestr_tasks = []
    status_only_rows = []
    for row in all_rows:
        tn = row['task_number']
        if tn not in existing:
            continue
        rn, task_detail = existing[tn]
        if task_detail == 'Разногласия':
            continue
        if rn and rn != 'Отклонён':
            # Строка с реальным номером реестра: полную перезапись пропускаем,
            # но «жизненные» поля (проверка/статус/биллинг) обновим отдельно.
            status_only_rows.append(row)
            continue
        update_rows.append(row)
        if rn == 'Отклонён':
            reset_reestr_tasks.append(tn)

    # ── Дедупликация по task_report_id ──
    # Кандидаты: входящие (new + update) и существующие активные, которые не перезаписываются.
    updated_task_numbers = {row['task_number'] for row in update_rows}

    candidates_by_report = {}
    for tri, group in active_by_report.items():
        for a in group:
            if a['task_number'] in updated_task_numbers:
                continue  # перезапишется входящей — кандидатом станет она
            candidates_by_report.setdefault(tri, []).append({
                'task_report_id': tri,
                'task_number': a['task_number'],
                'reestr_number': a['reestr_number'],
                'work_start_date': a['work_start_date'],
                'is_incoming': False,
            })

    for seq, row in enumerate(new_rows + update_rows):
        tri = row.get('task_report_id')
        if not tri:
            continue
        candidates_by_report.setdefault(tri, []).append({
            'task_report_id': tri,
            'task_number': row['task_number'],
            'reestr_number': None,
            'work_start_date': row.get('work_start_date'),
            'is_incoming': True,
            'seq': seq,
            'row': row,
        })

    loser_tasks = set()
    for cands in candidates_by_report.values():
        if len(cands) < 2:
            continue
        real_reestr = [c for c in cands if c['reestr_number'] and c['reestr_number'] != 'Отклонён']
        winner = real_reestr[0] if real_reestr else max(cands, key=_dup_key)
        for c in cands:
            if c is winner:
                continue
            loser_tasks.add(c['task_number'])
            if c['is_incoming']:
                c['row']['task_report'] = 'Дубли'
                c['row']['task_detail'] = 'Дубли'

    inserted = 0
    updated = 0

    if new_rows:
        batch_size = 1000
        columns_list = list(new_rows[0].keys())
        placeholders = ', '.join([':' + c for c in columns_list])
        columns_names = ', '.join(columns_list)

        for i in range(0, len(new_rows), batch_size):
            batch = new_rows[i:i + batch_size]
            await db_session.execute(
                text(f"INSERT INTO main_afl ({columns_names}) VALUES ({placeholders})"),
                batch
            )
            progress = 90 + int((i / len(new_rows)) * 9) if len(new_rows) > 0 else 99
            upload_progress[upload_id] = {
                "status": "merging", "progress": min(progress, 99),
                "total": total_rows, "inserted": min(i + batch_size, len(new_rows)),
                "updated": 0
            }
        inserted = len(new_rows)

    if update_rows:
        update_cols = [c for c in MAIN_AFL_COLUMNS if c != 'task_number']
        set_clause = ', '.join(f'"{c}" = :{c}' for c in update_cols)
        update_sql = text(f"UPDATE main_afl SET {set_clause} WHERE task_number = :task_number")
        await db_session.execute(update_sql, update_rows)
        updated = len(update_rows)

    if status_only_rows:
        status_set = ', '.join(f'"{c}" = :{c}' for c in STATUS_ONLY_COLUMNS)
        status_sql = text(f"UPDATE main_afl SET {status_set} WHERE task_number = :task_number")
        await db_session.execute(status_sql, status_only_rows)
        updated += len(status_only_rows)

    if reset_reestr_tasks:
        # 'Отклонён' сбрасываем в пустой — строка снова доступна для реестра.
        names, params = build_in_clause("rn", reset_reestr_tasks)
        await db_session.execute(
            text(f"UPDATE main_afl SET reestr_number = NULL, reestr_date = NULL WHERE task_number IN ({names})"),
            params
        )

    affected = [row['task_number'] for row in new_rows + update_rows]
    if affected:
        # Норматив ставим по факту загрузки строки; номер реестра лишь защищает её от перезаписи.
        await apply_norms(db_session, affected)

    if loser_tasks:
        # Проигравшие дедупликации → «Дубли»/«Отклонён» с нулевым нормативом (reestr_date не трогаем).
        names, params = build_in_clause("dup", list(loser_tasks))
        await db_session.execute(
            text(f"UPDATE main_afl SET task_report = 'Дубли', task_detail = 'Дубли', reestr_number = 'Отклонён', norm = 0, extra = 0 WHERE task_number IN ({names})"),
            params
        )

    await db_session.commit()

    upload_progress[upload_id] = {
        "status": "merging", "progress": 99, "total": total_rows,
        "inserted": inserted, "updated": updated
    }

    return inserted, updated, affected
