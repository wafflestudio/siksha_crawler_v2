from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


DEFAULT_URL = "https://snudorm.snu.ac.kr/foodmenu/"
SECTION_END_MARKER = "개인정보처리방침"
CAFETERIA_RE = re.compile(r"^(?P<name>.+?\(\d+동\))\s*(?P<rest>.*)$")
TIME_RE = re.compile(r"※\s*운영시간\s*:\s*(\d{2}:\d{2}~\d{2}:\d{2})")
PRICE_RE = re.compile(r"^(?P<menu>.+?)\s*:\s*(?P<price>[\d,]+원)$")
SECTION_MARKERS = ("식단 안내", "오늘의 식단")
HEADER_TOKENS = ("식당", "아침", "점심", "저녁")
BLOCK_TAGS = {
    "div",
    "p",
    "li",
    "ul",
    "ol",
    "section",
    "article",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "td",
    "th",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in BLOCK_TAGS or tag.lower() == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in BLOCK_TAGS:
            self.parts.append("\n")


def fetch_html(url: str) -> str:
    with urlopen(url, timeout=30) as response:
        encoding = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(encoding, errors="replace")


def html_to_lines(html: str) -> list[str]:
    parser = TextExtractor()
    parser.feed(html)
    raw_text = "".join(parser.parts).replace("\xa0", " ")
    lines: list[str] = []

    for line in raw_text.splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()
        if normalized:
            lines.append(normalized)

    return lines


def extract_menu_section(lines: list[str]) -> list[str]:
    start_index: int | None = None
    end_index: int | None = None
    anchor_index: int | None = None

    for index, line in enumerate(lines):
        if all(token in line for token in HEADER_TOKENS):
            start_index = index + 1
            break
        if anchor_index is None and any(marker in line for marker in SECTION_MARKERS):
            anchor_index = index

    if start_index is None and anchor_index is not None:
        for index in range(anchor_index + 1, len(lines)):
            if CAFETERIA_RE.match(lines[index]):
                start_index = index
                break

    if start_index is None:
        for index, line in enumerate(lines):
            if CAFETERIA_RE.match(line):
                start_index = index
                break

    if start_index is None:
        raise ValueError("식단 섹션 시작 지점을 찾지 못했습니다.")

    for index in range(start_index, len(lines)):
        if SECTION_END_MARKER in lines[index]:
            end_index = index
            break

    if end_index is None:
        raise ValueError("식단 섹션 종료 지점을 찾지 못했습니다.")

    return lines[start_index:end_index]


def split_cafeteria_blocks(section_lines: list[str]) -> list[dict[str, object]]:
    cafeterias: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for line in section_lines:
        match = CAFETERIA_RE.match(line)
        if match:
            current = {"name": match.group("name"), "lines": []}
            cafeterias.append(current)
            rest = match.group("rest").strip()
            if rest:
                current["lines"].append(rest)
            continue

        if current is not None:
            current["lines"].append(line)

    if not cafeterias:
        raise ValueError("식당 블록을 찾지 못했습니다.")

    return cafeterias


def meal_name_from_time(service_time: str) -> str:
    if service_time.startswith("08:"):
        return "breakfast"
    if service_time.startswith("11:") or service_time.startswith("12:"):
        return "lunch"
    if service_time.startswith("17:") or service_time.startswith("18:") or service_time.startswith("19:"):
        return "dinner"
    return "unknown"


def parse_menu_items(block_text: str) -> list[dict[str, str]]:
    items: list[dict[str, object]] = []

    for raw_line in block_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        price_match = PRICE_RE.match(line)
        if price_match:
            items.append(
                {
                    "이름": price_match.group("menu").strip(),
                    "가격": int(price_match.group("price").replace(",", "").replace("원", "")),
                }
            )
            continue

        items.append({"이름": line, "가격": None})

    return items


def clean_block_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def parse_cafeteria(name: str, lines: list[str]) -> dict[str, object]:
    joined = "\n".join(lines)
    parts = TIME_RE.split(joined)

    meals: dict[str, list[dict[str, object]]] = {"아침": [], "점심": [], "저녁": []}
    current_block = clean_block_text(parts[0]) if parts else ""

    for index in range(1, len(parts), 2):
        service_time = parts[index].strip()
        meal_name = meal_name_from_time(service_time)
        if current_block:
            localized_name = {"breakfast": "아침", "lunch": "점심", "dinner": "저녁"}.get(meal_name)
            if localized_name is not None:
                meals[localized_name].append({"메뉴": parse_menu_items(current_block)})
        current_block = clean_block_text(parts[index + 1]) if index + 1 < len(parts) else ""

    return {"name": name, "meals": meals}


def build_menu_json(url: str, html: str) -> dict[str, object]:
    lines = html_to_lines(html)
    section_lines = extract_menu_section(lines)
    cafeteria_blocks = split_cafeteria_blocks(section_lines)

    crawled_at = datetime.now().strftime("%Y-%m-%d")
    result: dict[str, object] = {}

    for block in cafeteria_blocks:
        cafeteria = parse_cafeteria(block["name"], block["lines"])  # type: ignore[index]
        result[cafeteria["name"]] = {crawled_at: cafeteria["meals"]}  # type: ignore[index]

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch the SNU dormitory menu page and convert it to JSON."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Target URL to crawl. Defaults to the SNU dormitory food menu page.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON result. Prints to stdout when omitted.",
    )
    args = parser.parse_args()

    try:
        html = fetch_html(args.url)
    except HTTPError as exc:
        print(f"HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc
    except URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        result = build_menu_json(args.url, html)
    except ValueError as exc:
        print(f"Parse error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    json_output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        args.output.write_text(json_output + "\n", encoding="utf-8")
        print(f"Wrote JSON to {args.output}")
        return

    print(json_output)


if __name__ == "__main__":
    main()
