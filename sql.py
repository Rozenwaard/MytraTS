"""SQL-хелперы общего назначения."""


def build_in_clause(prefix: str, values: list[str]) -> tuple[str, dict]:
    """Собирает IN (...) с bind-параметрами вида :prefix0, :prefix1, ..."""
    placeholders = {f"{prefix}{i}": v for i, v in enumerate(values)}
    names = ", ".join(f":{prefix}{i}" for i in range(len(values)))
    return names, placeholders
