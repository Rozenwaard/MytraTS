from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sql import build_in_clause

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


async def merge_to_main(db_session, upload_progress, upload_id, total_rows):
    # Существующие строки: task_number → текущий reestr_number.
    result = await db_session.execute(text("SELECT task_number, reestr_number FROM main_afl"))
    existing = {row[0]: row[1] for row in result}

    columns_str = ', '.join(f'"{c}"' for c in MAIN_AFL_COLUMNS)
    result = await db_session.execute(text(f"SELECT {columns_str} FROM raw_afl"))
    all_rows = [dict(row._mapping) for row in result]

    new_rows = [row for row in all_rows if row['task_number'] not in existing]

    # Перезаписываем только строки без номера реестра (пусто или 'Отклонён').
    # Строки с реальным номером реестра защищены и не обновляются.
    update_rows = []
    reset_reestr_tasks = []
    for row in all_rows:
        tn = row['task_number']
        if tn not in existing:
            continue
        rn = existing[tn]
        if rn and rn != 'Отклонён':
            continue
        update_rows.append(row)
        if rn == 'Отклонён':
            reset_reestr_tasks.append(tn)

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

    if reset_reestr_tasks:
        # 'Отклонён' сбрасываем в пустой — строка снова доступна для реестра.
        names, params = build_in_clause("rn", reset_reestr_tasks)
        await db_session.execute(
            text(f"UPDATE main_afl SET reestr_number = NULL, reestr_date = NULL WHERE task_number IN ({names})"),
            params
        )

    await db_session.commit()

    upload_progress[upload_id] = {
        "status": "complete", "progress": 100, "total": total_rows,
        "inserted": inserted, "updated": updated
    }

    affected = [row['task_number'] for row in new_rows + update_rows]
    return inserted, updated, affected
