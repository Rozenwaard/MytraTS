import json
from collections import Counter
from datetime import datetime
from urllib.parse import quote

from litestar import Router
from litestar.connection import Request
from litestar.handlers import get
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth
from sql import norm_name
from services.dashboard import build_scope, generate_errors_xlsx, generate_balance_xlsx, generate_task_numbers_xlsx, pick_pu_type
from services.report_check import split_errors, join_errors, BALANCE_ERRORS


@get("/dashboard/summary", guards=[require_auth])
async def api_dashboard_summary(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    zone_where = " AND ".join(clauses)

    total_rows = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {zone_where}"), params)).scalar()

    err_clauses = clauses + ["(errors IS NOT NULL AND errors != '')"]
    err_where = " AND ".join(err_clauses)
    with_errors = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {err_where}"), params)).scalar()

    billed_count = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {err_where} AND sent_to_billing = 'Да'"), params)).scalar()
    unbilled_count = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {err_where} AND sent_to_billing = 'Нет' AND status = 'Завершено'"), params)).scalar()

    unbilled_err_where = f"{err_where} AND sent_to_billing = 'Нет' AND status = 'Завершено'"
    result = await db_session.execute(text(f"SELECT errors FROM main_afl WHERE {unbilled_err_where}"), params)
    counter = Counter()
    for (errors_text,) in result:
        if errors_text:
            for e in split_errors(errors_text):
                counter[e] += 1

    errors_list = [{"label": label, "count": count} for label, count in counter.most_common()]
    return Response(content=json.dumps({
        "total_rows": total_rows,
        "with_errors": with_errors,
        "billed_count": billed_count,
        "unbilled_count": unbilled_count,
        "total_errors": sum(counter.values()),
        "errors": errors_list,
    }, ensure_ascii=False), media_type="application/json")


@get("/dashboard/overview", guards=[require_auth])
async def api_dashboard_overview(request: Request, db_session: AsyncSession) -> Response:
    """Сводка виджетов вкладки «Обзор» (по зоне видимости пользователя)."""
    user = await get_current_user(request, db_session)

    # Зона видимости по роли (без фильтров статуса/отчёта) — общая для всех срезов.
    vis_clauses: list = []
    vis_params: dict = {}
    if user.effective_role in ("оператор", "работник"):
        vis_clauses.append(f"{norm_name('executor')} IN (SELECT {norm_name('full_name')} FROM users WHERE locale = :locale)")
        vis_params["locale"] = user.locale
    elif user.effective_role == "менеджер":
        vis_clauses.append("executor_organization = :dept")
        vis_params["dept"] = user.dept
    vis_where = " AND ".join(vis_clauses) if vis_clauses else "1=1"

    base_where = "(report IS NULL OR report = '') AND status IN ('Завершено','Закрыто')"
    if vis_clauses:
        base_where += f" AND {vis_where}"
    params = vis_params

    # Стоимость = завершённые (status Завершено/Закрыто) строки без отчёта, по carte.price.
    cost = (await db_session.execute(
        text(f"SELECT COALESCE(SUM(COALESCE((SELECT price FROM carte WHERE carte.title = main_afl.task_report LIMIT 1), 0)), 0) FROM main_afl WHERE {base_where}"),
        params)).scalar()

    # Разбивка стоимости по заказчикам (customer = ПСК/РЛЭ) — для раскрытия плашки «Стоимость».
    cost_by_cust_result = await db_session.execute(
        text(f"SELECT customer, COALESCE(SUM(COALESCE((SELECT price FROM carte WHERE carte.title = main_afl.task_report LIMIT 1), 0)), 0) FROM main_afl WHERE {base_where} GROUP BY customer"),
        params)
    cost_by_cust = {row[0]: (row[1] or 0) for row in cost_by_cust_result}

    # «Заданий в работе»: строки со статусом не «Завершено»/«Закрыто» (status NOT LIKE 'З%').
    in_work_where = f"{vis_where} AND (status IS NULL OR status NOT LIKE 'З%')"

    # Матрица 2×2 «Заданий в работе»: ПСК/РЛЭ × План/Внеплан.
    in_work_matrix_result = await db_session.execute(
        text(f"SELECT customer, task_type, COUNT(*) FROM main_afl WHERE {in_work_where} AND task_type IN ('Плановый','Внеплановый') GROUP BY customer, task_type"),
        vis_params)
    in_work_matrix = {"psk_plan": 0, "psk_unplan": 0, "rle_plan": 0, "rle_unplan": 0}
    for cust, task_type, cnt in in_work_matrix_result:
        cust_key = "psk" if cust == "ПСК" else ("rle" if cust == "РЛЭ" else None)
        task_key = "plan" if task_type == "Плановый" else ("unplan" if task_type == "Внеплановый" else None)
        if cust_key and task_key:
            in_work_matrix[f"{cust_key}_{task_key}"] = cnt

    # «Крупная задолженность»: visit_reason содержит «Крупная задолженность».
    # Матрица 2×2: просрочено/вовремя × в работе/выполнено.
    #   просрочено = не завершено за 7 дней от создания: «в работе» — создано раньше 7 дней назад;
    #                «выполнено» — выполнено позже чем через 7 дней после создания (done_day - created_at > 7).
    debt_clause = f"{vis_where} AND visit_reason LIKE :debt_reason"
    debt_params = {**vis_params, "debt_reason": "%Крупная задолженность%"}
    debt_total, ontime_in_work, ontime_completed, overdue_in_work, overdue_completed = (await db_session.execute(text(
        f"SELECT COUNT(*), "
        f"COALESCE(SUM(CASE WHEN (status IS NULL OR status NOT LIKE 'З%') AND (created_at IS NULL OR created_at > date('now', 'localtime', '-7 days')) THEN 1 ELSE 0 END), 0), "
        f"COALESCE(SUM(CASE WHEN (status IS NOT NULL AND status LIKE 'З%') AND (done_day IS NULL OR created_at IS NULL OR julianday(done_day) - julianday(created_at) <= 7) THEN 1 ELSE 0 END), 0), "
        f"COALESCE(SUM(CASE WHEN (status IS NULL OR status NOT LIKE 'З%') AND (created_at IS NOT NULL AND created_at <= date('now', 'localtime', '-7 days')) THEN 1 ELSE 0 END), 0), "
        f"COALESCE(SUM(CASE WHEN (status IS NOT NULL AND status LIKE 'З%') AND (done_day IS NOT NULL AND created_at IS NOT NULL AND julianday(done_day) - julianday(created_at) > 7) THEN 1 ELSE 0 END), 0) "
        f"FROM main_afl WHERE {debt_clause}"
    ), debt_params)).one()

    # «Работники»: контролёры (position содержит «контролёр») и инженеры (position содержит «инженер»)
    # — по различным исполнителям за последние 10 дней работ (done_day), в зоне видимости пользователя.
    workers_clauses: list = []
    if user.effective_role in ("оператор", "работник"):
        workers_clauses.append(f"{norm_name('m.executor')} IN (SELECT {norm_name('full_name')} FROM users WHERE locale = :locale)")
    elif user.effective_role == "менеджер":
        workers_clauses.append("m.executor_organization = :dept")
    workers_where = " AND ".join(workers_clauses) if workers_clauses else "1=1"

    workers_controllers, workers_engineers = (await db_session.execute(text(
        "WITH last_days AS ("
        "  SELECT DISTINCT done_day FROM main_afl WHERE done_day IS NOT NULL AND done_day != '' ORDER BY done_day DESC LIMIT 10"
        ") "
        "SELECT "
        "COUNT(DISTINCT CASE WHEN u.position LIKE '%онтролёр%' THEN m.executor END), "
        "COUNT(DISTINCT CASE WHEN u.position LIKE '%нженер%' THEN m.executor END) "
        "FROM main_afl m "
        "JOIN users u ON REPLACE(REPLACE(u.full_name,'ё','е'),'Ё','Е') = REPLACE(REPLACE(m.executor,'ё','е'),'Ё','Е') "
        f"WHERE m.done_day IN (SELECT done_day FROM last_days) AND {workers_where}"
    ), vis_params)).one()

    # «Инструментальные проверки»: заказано (все строки вида работ) / выполнено (status Завершено/Закрыто).
    instr_clause = f"{vis_where} AND work_type_in_task = 'Инструментальная проверка'"
    instr_ordered = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {instr_clause}"), vis_params)).scalar()
    instr_completed = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {instr_clause} AND task_report IN (SELECT title FROM carte WHERE kind = 'base')"), vis_params)).scalar()

    # «Дубли»: точки учёта, встречающиеся более 1 раза среди строк «в работе»
    # (status не «Завершено»/«Закрыто»). Разбивка по task_source:
    #   «Только CRM» — все строки точки учёта пришли из CRM;
    #   «Смешанные»  — среди строк точки учёта есть и CRM, и другие источники;
    #   «Не CRM»      — среди строк точки учёта нет CRM.
    dup_base = "metering_point IS NOT NULL AND metering_point != '' AND (status IS NULL OR status NOT LIKE 'З%')"
    duplicates_crm = (await db_session.execute(
        text(
            f"SELECT COUNT(*) FROM ("
            f"SELECT metering_point FROM main_afl WHERE {vis_where} AND {dup_base} "
            f"GROUP BY metering_point "
            f"HAVING COUNT(*) > 1 AND SUM(CASE WHEN task_source = 'CRM' THEN 1 ELSE 0 END) = COUNT(*)"
            f")"
        ), vis_params)).scalar()
    duplicates_mixed = (await db_session.execute(
        text(
            f"SELECT COUNT(*) FROM ("
            f"SELECT metering_point FROM main_afl WHERE {vis_where} AND {dup_base} "
            f"GROUP BY metering_point "
            f"HAVING COUNT(*) > 1 AND SUM(CASE WHEN task_source = 'CRM' THEN 1 ELSE 0 END) > 0 "
            f"AND SUM(CASE WHEN task_source = 'CRM' THEN 1 ELSE 0 END) < COUNT(*)"
            f")"
        ), vis_params)).scalar()
    duplicates_nocrm = (await db_session.execute(
        text(
            f"SELECT COUNT(*) FROM ("
            f"SELECT metering_point FROM main_afl WHERE {vis_where} AND {dup_base} "
            f"GROUP BY metering_point "
            f"HAVING COUNT(*) > 1 AND SUM(CASE WHEN task_source = 'CRM' THEN 1 ELSE 0 END) = 0"
            f")"
        ), vis_params)).scalar()

    return Response(content=json.dumps({
        "cost": round(cost, 2),
        "cost_psk": round(cost_by_cust.get("ПСК", 0), 2),
        "cost_rle": round(cost_by_cust.get("РЛЭ", 0), 2),
        "in_work_matrix": in_work_matrix,
        "debt": {
            "total": debt_total,
            "ontime_in_work": ontime_in_work,
            "ontime_completed": ontime_completed,
            "overdue_in_work": overdue_in_work,
            "overdue_completed": overdue_completed,
        },
        "workers": {
            "total": workers_controllers + workers_engineers,
            "controllers": workers_controllers,
            "engineers": workers_engineers,
        },
        "instrumental": {
            "ordered": instr_ordered,
            "completed": instr_completed,
        },
        "duplicates": {
            "crm": duplicates_crm,
            "mixed": duplicates_mixed,
            "non_crm": duplicates_nocrm,
        },
    }, ensure_ascii=False), media_type="application/json")


@get("/dashboard/errors-report", guards=[require_auth])
async def api_dashboard_errors_report(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    clauses.append("(errors IS NOT NULL AND errors != '')")
    clauses.append("sent_to_billing = 'Нет' AND status = 'Завершено'")
    where = " AND ".join(clauses)

    result = await db_session.execute(
        text(f"SELECT task_number, errors FROM main_afl WHERE {where} ORDER BY task_number"), params)

    # Балансовые ошибки и «Дата работ» сюда не входят — по ним отдельные выгрузки.
    excluded = BALANCE_ERRORS | {"Дата работ"}
    rows = []
    for tn, errors_text in result:
        kept = [e for e in split_errors(errors_text) if e not in excluded]
        if kept:
            rows.append((tn, join_errors(kept)))

    output = generate_errors_xlsx(rows)
    filename = f"Отчёт_об_ошибках_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@get("/dashboard/balance-report", guards=[require_auth])
async def api_dashboard_balance_report(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    clauses.append("errors LIKE :be")
    clauses.append("sent_to_billing = 'Нет' AND status = 'Завершено'")
    params["be"] = "%Балансовая принадлежность%"
    where = " AND ".join(clauses)

    result = await db_session.execute(
        text(f"SELECT task_number, meter_type_2, meter_type_1, meter_type FROM main_afl WHERE {where} ORDER BY task_number"), params)
    rows = [(r[0], pick_pu_type(r[1], r[2], r[3])) for r in result]

    output = generate_balance_xlsx(rows)
    filename = f"Балансовая_принадлежность_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@get("/dashboard/date-report", guards=[require_auth])
async def api_dashboard_date_report(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    clauses.append("errors LIKE :dw")
    clauses.append("sent_to_billing = 'Нет' AND status = 'Завершено'")
    params["dw"] = "%Дата работ%"
    where = " AND ".join(clauses)

    result = await db_session.execute(
        text(f"SELECT task_number FROM main_afl WHERE {where} ORDER BY task_number"), params)
    rows = [r[0] for r in result]

    output = generate_task_numbers_xlsx(rows)
    filename = f"Дата_работ_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@get("/dashboard/verified-report", guards=[require_auth])
async def api_dashboard_verified_report(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    clauses.append("verified = 'Нет'")
    clauses.append("sent_to_billing = 'Нет' AND status = 'Завершено'")
    clauses.append("(errors IS NULL OR errors = '')")
    where = " AND ".join(clauses)

    result = await db_session.execute(
        text(f"SELECT task_number FROM main_afl WHERE {where} ORDER BY task_number"), params)
    rows = [r[0] for r in result]

    output = generate_task_numbers_xlsx(rows)
    filename = f"Отметка_о_проверке_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@get("/dashboard/report-counts", guards=[require_auth])
async def api_dashboard_report_counts(request: Request, db_session: AsyncSession) -> Response:
    """Число строк в отчётах «Балансовая», «Дата работ», «Отметка о проверке», «Отчёт об ошибках» (зона стоп-фактора + видимость роли)."""
    user = await get_current_user(request, db_session)
    base, base_params = build_scope(user, "")

    counts: dict = {}
    specs = [
        ("balance", ["errors LIKE :be"], {"be": "%Балансовая принадлежность%"}),
        ("date", ["errors LIKE :dw"], {"dw": "%Дата работ%"}),
        ("verified", ["verified = 'Нет'", "(errors IS NULL OR errors = '')"], {}),
    ]
    for label, extra_clauses, extra_params in specs:
        clauses = base + extra_clauses + ["sent_to_billing = 'Нет' AND status = 'Завершено'"]
        params = {**base_params, **extra_params}
        where = " AND ".join(clauses)
        counts[label] = (await db_session.execute(
            text(f"SELECT COUNT(*) FROM main_afl WHERE {where}"), params)).scalar()

    # «Отчёт об ошибках»: строки с ошибками, кроме балансовых и «Дата работ» (считаем в Python, как в выгрузке).
    err_clauses = base + ["(errors IS NOT NULL AND errors != '')", "sent_to_billing = 'Нет' AND status = 'Завершено'"]
    err_where = " AND ".join(err_clauses)
    result = await db_session.execute(
        text(f"SELECT errors FROM main_afl WHERE {err_where}"), base_params)
    excluded = BALANCE_ERRORS | {"Дата работ"}
    counts["errors"] = sum(
        1 for (errors_text,) in result
        if any(e not in excluded for e in split_errors(errors_text))
    )

    return Response(content=json.dumps(counts, ensure_ascii=False), media_type="application/json")


@get("/dashboard/errors-by-locale", guards=[require_auth])
async def api_dashboard_errors_by_locale(request: Request, db_session: AsyncSession) -> Response:
    """Строки с ошибками «на исправлении» в зоне стоп-фактора — по группам (locale)."""
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, "")
    clauses.append("(errors IS NOT NULL AND errors != '')")
    clauses.append("sent_to_billing = 'Нет' AND status = 'Завершено'")
    where = " AND ".join(clauses)

    locale_expr = (
        f"COALESCE((SELECT locale FROM users WHERE {norm_name('users.full_name')} = {norm_name('main_afl.executor')} LIMIT 1), '(без локали)')"
    )
    result = await db_session.execute(text(
        f"SELECT {locale_expr} AS locale, COUNT(*) AS cnt FROM main_afl WHERE {where} GROUP BY locale ORDER BY cnt DESC"
    ), params)
    by_locale = [{"locale": row[0], "count": row[1]} for row in result]

    return Response(content=json.dumps(
        {"total": sum(item["count"] for item in by_locale), "by_locale": by_locale},
        ensure_ascii=False), media_type="application/json")


dashboard_router = Router("/api", route_handlers=[
    api_dashboard_summary, api_dashboard_overview, api_dashboard_errors_report,
    api_dashboard_balance_report, api_dashboard_date_report, api_dashboard_verified_report,
    api_dashboard_report_counts, api_dashboard_errors_by_locale,
])
