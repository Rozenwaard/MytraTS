# -*- coding: utf-8 -*-
"""Дашборд: сводка ошибок и выгрузка отчётов по территориям стоп-фактора."""
import io

from openpyxl import Workbook

from sql import norm_name
from services.report_check import STOP_FACTOR_REGIONS, STOP_FACTOR_DISTRICTS


def build_scope(user, dept: str = "") -> tuple[list, dict]:
    """Зона видимости: территории стоп-фактора + виды работ из carte.kind='base' + (отделение) + видимость по роли (все заказчики)."""
    clauses: list[str] = []
    params: dict = {}

    if dept:
        clauses.append("executor_organization = :dept_filter")
        params["dept_filter"] = dept

    clauses.append("task_report IN (SELECT title FROM carte WHERE kind = 'base')")

    regions = sorted(STOP_FACTOR_REGIONS)
    districts = sorted(STOP_FACTOR_DISTRICTS)
    r_names = [f"sfr{i}" for i in range(len(regions))]
    d_names = [f"sfd{i}" for i in range(len(districts))]
    params.update(zip(r_names, regions))
    params.update(zip(d_names, districts))
    r_in = ", ".join(f":{n}" for n in r_names)
    d_in = ", ".join(f":{n}" for n in d_names)
    clauses.append(f"(region IN ({r_in}) OR municipal_district IN ({d_in}))")

    role = user.effective_role
    if role in ("оператор", "работник"):
        clauses.append(f"{norm_name('executor')} IN (SELECT {norm_name('full_name')} FROM users WHERE locale = :locale)")
        params["locale"] = user.locale
    elif role == "менеджер":
        clauses.append("executor_organization = :dept")
        params["dept"] = user.dept

    return clauses, params


def pick_pu_type(meter_type_2, meter_type_1, meter_type):
    for v in (meter_type_2, meter_type_1, meter_type):
        if v and str(v).strip():
            return str(v).strip()
    return ""


def generate_errors_xlsx(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ошибки"
    ws.append(["Номер задания", "Ошибки"])
    for tn, errors in rows:
        ws.append([tn, errors])
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 90
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_balance_xlsx(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Балансовая принадлежность"
    ws.append(["Номер задания", "Тип ПУ"])
    for tn, pu_type in rows:
        ws.append([tn, pu_type])
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 30
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_task_numbers_xlsx(rows) -> bytes:
    """Отчёт из одного столбца «Номер задания» (для «Дата работ» и «Отметка о проверке»)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Задания"
    ws.append(["Номер задания"])
    for tn in rows:
        ws.append([tn])
    ws.column_dimensions["A"].width = 28
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_recheck_xlsx(rows, balance_rows, date_rows) -> bytes:
    """Отчёт «Повторная проверка»: 3 вкладки — общие ошибки, балансовая принадлежность, дата работ."""
    wb = Workbook()

    ws = wb.active
    ws.title = "Ошибки"
    ws.append(["Номер задания", "Ошибки", "Комментарий"])
    for tn, errors, comment in rows:
        ws.append([tn, errors, comment])
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 90
    ws.column_dimensions["C"].width = 30

    ws_balance = wb.create_sheet("Балансовая принадлежность")
    ws_balance.append(["Номер задания", "Комментарий"])
    for tn, comment in balance_rows:
        ws_balance.append([tn, comment])
    ws_balance.column_dimensions["A"].width = 28
    ws_balance.column_dimensions["B"].width = 60

    ws_date = wb.create_sheet("Дата работ")
    ws_date.append(["Номер задания", "Комментарий"])
    for tn, comment in date_rows:
        ws_date.append([tn, comment])
    ws_date.column_dimensions["A"].width = 28
    ws_date.column_dimensions["B"].width = 60

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
