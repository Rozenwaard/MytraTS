# -*- coding: utf-8 -*-
"""Дашборд: сводка ошибок и выгрузка отчётов по территориям стоп-фактора."""
import io

from openpyxl import Workbook

from services.report_check import STOP_FACTOR_REGIONS, STOP_FACTOR_DISTRICTS


def build_scope(user) -> tuple[list, dict]:
    """Зона видимости пользователя + территории стоп-фактора + только строки с ошибками."""
    clauses = ["customer = 'ПСК'", "(errors IS NOT NULL AND errors != '')"]
    params: dict = {}

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
        clauses.append("executor IN (SELECT full_name FROM users WHERE locale = :locale)")
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
