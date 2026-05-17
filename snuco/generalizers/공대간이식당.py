import re
from typing import Any


PRICE_RE = re.compile(r"^(?P<name>.+?)\s*:\s*(?P<price>[\d,]+)\s*원")


def parse_lines(lines: list[str]) -> list[dict[str, Any]]:
    meals = []
    for line in lines:
        if line.startswith("※") or line.startswith("<"):
            continue

        match = PRICE_RE.match(line)
        if match is None:
            continue

        name = match.group("name").strip()
        price = 8300 if name == "호구세트" else int(match.group("price").replace(",", ""))
        meals.append({"price": price, "noMeat": False, "menus": [name]})
    return meals


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals = parse_lines(lines)
        if meals:
            payloads.append({"type": meal_type, "meals": meals})
    return payloads
