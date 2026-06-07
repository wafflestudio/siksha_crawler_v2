import re
from typing import Any


PRICE_RE = re.compile(r"^(?P<name>.+?)\s*:\s*(?P<price>[\d,]+)\s*원")
SPLIT_RE = re.compile(r"\s*[,&*]\s*")
SECTION_RE = re.compile(r"^<(?P<section>[^>]+)>\s*(?P<body>.*)$")
SECTION_TO_CORNER = {
    "A코너": "A코너",
    "B코너": "B코너",
    "C코너": "C코너",
    "직화코너": "직화코너",
}


def normalize_names(name_text: str) -> list[str]:
    name_text = re.sub(r"^<[^>]+>", "", name_text)
    name_text = name_text.replace("(#)", "").replace("[#]", "").strip()
    return [name for part in SPLIT_RE.split(name_text) if (name := part.strip())]


def parse_price_line(line: str) -> dict[str, Any] | None:
    match = PRICE_RE.match(line)
    if match is None:
        return None

    names = normalize_names(match.group("name"))
    if not names:
        return None

    return {
        "price": int(match.group("price").replace(",", "")),
        "noMeat": False,
        "menus": names,
    }


def parse_lines(meal_type: str, lines: list[str]) -> dict[str, list[dict[str, Any]]]:
    meals_by_corner: dict[str, list[dict[str, Any]]] = {}
    current_corner: str | None = "직화코너" if meal_type == "DINNER" else None

    for line in lines:
        if line.startswith("※"):
            continue

        section_match = SECTION_RE.match(line)
        if section_match is not None:
            current_corner = SECTION_TO_CORNER.get(section_match.group("section").strip(), current_corner)
            line = section_match.group("body").strip()
            if not line:
                continue

        if current_corner is None and line.startswith("철판)"):
            current_corner = "직화코너"

        if current_corner is None:
            continue

        meal = parse_price_line(line)
        if meal is None:
            continue

        meals_by_corner.setdefault(current_corner, []).append(meal)

    return meals_by_corner


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals_by_corner = parse_lines(meal_type, lines)
        for corner, meals in meals_by_corner.items():
            if meals:
                payloads.append({"corner": corner, "type": meal_type, "meals": meals})
    return payloads
