import re
from typing import Any


PRICE_RE = re.compile(r"^(?P<name>.+?)\s*(?::|-)\s*(?P<price>[\d,]+)\s*원")


def clean_name(name_text: str) -> str:
    name_text = re.sub(r"\s*\(순살변경.*?\)", "", name_text)
    name_text = re.sub(r"\s*/\s*매운맛 변경.*$", "", name_text)
    return name_text.strip()


def parse_lines(lines: list[str]) -> list[dict[str, Any]]:
    meals = []
    for line in lines:
        if line.startswith("※") or line.startswith("<"):
            continue

        match = PRICE_RE.match(line)
        if match is None:
            continue

        name = clean_name(match.group("name"))
        if name:
            meals.append({
                "price": int(match.group("price").replace(",", "")),
                "noMeat": False,
                "menus": [name],
            })
    return meals


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals = parse_lines(lines)
        if meals:
            payloads.append({"type": meal_type, "meals": meals})
    return payloads
