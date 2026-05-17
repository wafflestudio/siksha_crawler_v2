import re
from typing import Any


BUFFET_RE = re.compile(r"^<셀프코너>\s*(?P<price>[\d,]+)\s*원")
PRICE_RE = re.compile(r"^(?P<name>.+?)\s*:\s*(?P<price>[\d,]+)\s*원")
SPLIT_RE = re.compile(r"\s*[,&*]\s*")


def normalize_names(name_text: str) -> list[str]:
    name_text = name_text.replace("(#)", "").replace("[#]", "").strip()
    return [name for part in SPLIT_RE.split(name_text) if (name := part.strip())]


def parse_lines(lines: list[str]) -> list[dict[str, Any]]:
    meals = []
    buffet_price: int | None = None
    buffet_items: list[str] = []

    def flush_buffet() -> None:
        nonlocal buffet_price, buffet_items
        if buffet_items:
            meals.append({"price": buffet_price, "noMeat": False, "menus": buffet_items})
        buffet_price = None
        buffet_items = []

    for line in lines:
        if line.startswith("※"):
            continue

        buffet_match = BUFFET_RE.match(line)
        if buffet_match is not None:
            flush_buffet()
            buffet_price = int(buffet_match.group("price").replace(",", ""))
            continue

        if line == "<주문식 메뉴>":
            flush_buffet()
            continue

        price_match = PRICE_RE.match(line)
        if price_match is not None:
            flush_buffet()
            names = normalize_names(price_match.group("name"))
            if names:
                meals.append({
                    "price": int(price_match.group("price").replace(",", "")),
                    "noMeat": False,
                    "menus": names,
                })
            continue

        if buffet_price is not None:
            buffet_items.extend(normalize_names(line))

    flush_buffet()
    return meals


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals = parse_lines(lines)
        if meals:
            payloads.append({"type": meal_type, "meals": meals})
    return payloads
