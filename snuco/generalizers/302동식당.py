import re
from typing import Any


BUFFET_RE = re.compile(r"^<뷔페>\s*(?P<price>[\d,]+)\s*원")
SPLIT_RE = re.compile(r"\s*[,&*]\s*")


def normalize_names(name_text: str) -> list[str]:
    name_text = name_text.replace("(#)", "").replace("[#]", "").strip()
    return [name for part in SPLIT_RE.split(name_text) if (name := part.strip())]


def parse_lines(lines: list[str]) -> list[dict[str, Any]]:
    meals = []
    buffet_price: int | None = None
    buffet_items: list[str] = []

    for line in lines:
        if line.startswith("※"):
            continue

        buffet_match = BUFFET_RE.match(line)
        if buffet_match is not None:
            if buffet_items:
                meals.append({"price": buffet_price, "noMeat": False, "menus": buffet_items})
            buffet_price = int(buffet_match.group("price").replace(",", ""))
            buffet_items = []
            continue

        if buffet_price is not None:
            buffet_items.extend(normalize_names(line))

    if buffet_items:
        meals.append({"price": buffet_price, "noMeat": False, "menus": buffet_items})

    return meals


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals = parse_lines(lines)
        if meals:
            payloads.append({"type": meal_type, "meals": meals})
    return payloads
