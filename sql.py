"""SQL-хелперы общего назначения."""

import re


def regexp(expr: str, item) -> bool:
    """Функция REGEXP для SQLite (перенесена из services.processor — B4)."""
    if item is None:
        return False
    try:
        return re.search(expr, item) is not None
    except Exception:
        return False


def build_in_clause(prefix: str, values: list[str]) -> tuple[str, dict]:
    """Собирает IN (...) с bind-параметрами вида :prefix0, :prefix1, ..."""
    placeholders = {f"{prefix}{i}": v for i, v in enumerate(values)}
    names = ", ".join(f":{prefix}{i}" for i in range(len(values)))
    return names, placeholders


def norm_name(column: str) -> str:
    """SQL-выражение нормализации ФИО «ё/е» для сравнения (данные в БД не меняем)."""
    return f"REPLACE(REPLACE({column}, 'ё', 'е'), 'Ё', 'Е')"


def clean_text(value) -> str | None:
    """Обрезает краевые пробелы, приводит неразрывные пробелы (NBSP и др.) к обычным
    и схлопывает внутренние пробельные серии. Пустая строка → None."""
    if value is None:
        return None
    s = str(value)
    for ch in ("\xa0", "\u2007", "\u202f"):
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    return s or None
