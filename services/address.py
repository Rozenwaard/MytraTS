"""Нормализация адреса → ключ дома (регион + населённый пункт + улица + дом + корпус).

Ключ строится по адресной строке main_afl.address + main_afl.region.
Если дом обособить не удалось (нет города или нет номера дома) — возвращаем None
(«неидентифицируемый» объект, SLA полноты к нему не применяется).
"""

import re

CITY_TYPES = r"(?:пгт|пос|дер|снт|квартал|кв-л|массив|остров|тер|уч|гп|кп|г|п|с|д|ст|х|м)\.?"
STREET_TYPES = r"(?:проезд|пр-кт|пр-д|проспект|бульвар|аллея|площадь|шоссе|набережная|пер|наб|туп|линия|мкр|б-р|пл|ш|ул|пр|дор)\.?"


def _norm(value: str) -> str:
    """Нормализация отдельного компонента ключа: в нижний регистр, без лишних пробелов."""
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _normalize_addr(addr: str) -> str:
    s = (addr or "").strip()
    s = re.sub(r"\s+", " ", s)            # схлопнуть пробелы
    s = re.sub(r",(?!\s)", ", ", s)       # вставить пробел после запятой
    s = re.sub(r"^\d{6}[\s,]+", "", s)    # убрать почтовый индекс
    return s


def _extract_city(s: str) -> str | None:
    m = re.search(rf"(?:^|,\s*){CITY_TYPES}\s*(.+?)\s*$", s, flags=re.I)
    return m.group(1).strip() if m else None


def parse_address(addr: str) -> dict | None:
    """Разбирает адрес → {city, street, house, corpus, flat}. Нет города/дома → None."""
    s = _normalize_addr(addr)
    if not s:
        return None
    for prefix in ("обл", "р-н", "край", "респ", "округ"):
        s = re.sub(rf"^{prefix}\.?\s*[^,]+,?\s*", "", s)
    # форма «ЛЕНИНГРАДСКАЯ обл., ВСЕВОЛОЖСКИЙ РАЙОН, …» — регион/район в любом написании
    for _ in range(4):
        s2 = re.sub(r"^[^,]*?(?:обл|р-н|район|край|респ|округ)[^,]*,\s*", "", s, flags=re.I)
        if s2 == s:
            break
        s = s2

    flat = None
    m = re.search(r",\s*кв\.?\s*(.+?)\s*$", s)
    if m:
        flat = m.group(1).strip()
        s = s[:m.start()].strip()

    house = None
    corpus = None
    m = re.search(r",\s*д\.?\s*(.+?)\s*$", s)
    if m:
        hr = m.group(1).strip()
        s = s[:m.start()].strip()
        cm = re.search(r"^(.*?)\s+(?:корпус|кор\.?|к\.?)\s*(.+)$", hr)
        if cm:
            hr = cm.group(1).strip()
            corpus = cm.group(2).strip()
        house = hr.rstrip(",.").strip()
        if corpus:
            corpus = corpus.rstrip(",.").strip()

    # слипшаяся форма «ул.Школьнаяд.1» (улица + дом без запятой)
    if house is None:
        m = re.search(rf"^(.*?),\s*{STREET_TYPES}\s*(.+?)\s*д\.?\s*(\S+)\s*$", s, flags=re.I)
        if m:
            citypart = m.group(1)
            street = m.group(2).strip()
            house = m.group(3)
            city = _extract_city(citypart)
            return {"city": city, "street": street, "house": house, "corpus": None, "flat": flat}

    street = None
    m = re.search(rf",\s*{STREET_TYPES}\s*(.+?)\s*$", s, flags=re.I)
    if m:
        street = m.group(1).strip()
        s = s[:m.start()].strip()

    # «ул. Кирпичстрой 4» — дом без «д.», просто номер в конце улицы
    if house is None and street:
        hm = re.search(r"^(.*?)\s+(\d+\s*-?[а-яё]?)\s*$", street, re.I)
        if hm:
            street = hm.group(1).strip()
            house = hm.group(2).strip()

    city = _extract_city(s)

    # «д. 23, к.3» — корпус в отдельном сегменте уже распознан выше; здесь fallback не нужен.
    if house is None:
        return None
    return {"city": city, "street": street, "house": house, "corpus": corpus, "flat": flat}


def region_from(municipal_district: str | None, addr: str | None) -> str | None:
    """Регион: 'ЛО' / 'СПб'. Основной источник — municipal_district, фолбэк — адрес."""
    md = municipal_district or ""
    a = addr or ""
    if "СПб" in md or "Санкт-Петербург" in md or "Санкт" in md:
        return "СПб"
    if md.startswith("ЛО") or "Ленинград" in md:
        return "ЛО"
    if "Санкт-Петербург" in a or "СПб" in a:
        return "СПб"
    if "Ленинградск" in a:
        return "ЛО"
    return None


def house(region: str | None, addr: str) -> dict | None:
    """Полные компоненты дома + ключ. Не обособили → None."""
    p = parse_address(addr)
    if not p or not p["city"] or not p["house"]:
        return None
    r = _norm(region)
    city = _norm(p["city"])
    street = _norm(p["street"])
    h = _norm(p["house"])
    corpus = _norm(p["corpus"])
    return {
        "region": r,
        "city": city,
        "street": street,
        "house": h,
        "corpus": corpus,
        "key": "|".join([r, city, street, h, corpus]),
    }


def house_key(region: str | None, addr: str) -> str | None:
    """Ключ дома: регион|город|улица|дом|корпус. Не обособили → None."""
    h = house(region, addr)
    return h["key"] if h else None

