import re
from typing import Any


PRICE_RE = re.compile(r"^(?P<name>.+?)\s*:?\s*(?P<price>[\d,]+)\s*원")
SPLIT_RE = re.compile(r"\s*[,&+*]\s*")


def normalize_names(name_text: str) -> list[str]:
    name_text = name_text.replace("(#)", "").replace("[#]", "").strip()
    return [name for part in SPLIT_RE.split(name_text) if (name := part.strip())]


def parse_lines(lines: list[str]) -> list[dict[str, Any]]:
    meals = []
    for line in lines:
        if line.startswith("※") or line.startswith("<"):
            continue

        match = PRICE_RE.match(line)
        if match is None:
            continue

        names = normalize_names(match.group("name"))
        if names:
            meals.append({
                "price": int(match.group("price").replace(",", "")),
                "noMeat": False,
                "menus": names,
            })
    return meals


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals = parse_lines(lines)
        if meals:
            payloads.append({"type": meal_type, "meals": meals})
    return payloads
