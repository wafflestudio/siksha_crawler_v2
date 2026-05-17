import re
from typing import Any


PRICE_RE = re.compile(r"^(?P<name>.+?)\s*:\s*(?P<price>[\d,]+)\s*원")
SPLIT_RE = re.compile(r"\s*[,&*]\s*")


def normalize_names(name_text: str) -> list[str]:
    name_text = name_text.replace("(#)", "").replace("[#]", "").strip()
    return [name for part in SPLIT_RE.split(name_text) if (name := part.strip())]


def parse_lines(lines: list[str]) -> list[dict[str, Any]]:
    meals = []
    buffet_items = []
    in_semi_buffet = False

    for line in lines:
        if line.startswith("※"):
            continue
        if "뷔페 특성상" in line or "가능성이 있으니" in line:
            continue
        if line == "<+세미뷔페>":
            in_semi_buffet = True
            continue

        match = PRICE_RE.match(line)
        if match is not None:
            names = normalize_names(match.group("name"))
            if names:
                meals.append({
                    "price": int(match.group("price").replace(",", "")),
                    "noMeat": False,
                    "menus": names,
                })
            continue

        if in_semi_buffet:
            buffet_items.extend(normalize_names(line))

    if buffet_items:
        meals.append({"price": None, "noMeat": False, "menus": buffet_items})

    return meals


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals = parse_lines(lines)
        if meals:
            payloads.append({"type": meal_type, "meals": meals})
    return payloads
