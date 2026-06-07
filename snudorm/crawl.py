import re
import sys
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode

import pytz
import requests
import urllib3

sys.path.append(str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common.types import Payload
from snudorm.generalizers import 생협기숙사, 아워홈


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_URL = "https://snudorm.snu.ac.kr/foodmenu/"
CRAWL_DAYS_AHEAD = 7
KST = pytz.timezone("Asia/Seoul")
SECTION_END_MARKER = "개인정보처리방침"
CAFETERIA_NAMES = (
    "아워홈(901동)",
    "생협기숙사(919동)",
)
CAFETERIA_GENERALIZERS = {
    CAFETERIA_NAMES[0]: 아워홈,
    CAFETERIA_NAMES[1]: 생협기숙사,
}
CAFETERIA_METADATA = {
    "아워홈(901동)": {"buildingNumber": "901동", "buildingName": None, "restaurant": "아워홈"},
    "생협기숙사(919동)": {"buildingNumber": "919동", "buildingName": "관악생활관", "restaurant": "생협기숙사"},
}
BLOCK_TAGS = {
    "div", "p", "li", "ul", "ol", "section", "article",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th",
    "h1", "h2", "h3", "h4", "h5", "h6",
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
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    if not response.encoding:
        response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def menu_url(menu_date: str) -> str:
    return f"{DEFAULT_URL}?{urlencode({'date': menu_date})}"


def menu_dates(days_ahead: int = CRAWL_DAYS_AHEAD) -> list[str]:
    start_date = datetime.now(KST).date()
    return [
        (start_date + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(days_ahead + 1)
    ]


def html_to_lines(html: str) -> list[str]:
    parser = TextExtractor()
    parser.feed(html)
    raw_text = "".join(parser.parts).replace("\xa0", " ")
    return [
        normalized
        for line in raw_text.splitlines()
        if (normalized := re.sub(r"\s+", " ", line).strip())
    ]


def extract_menu_section(lines: list[str]) -> list[str]:
    end_index: int | None = None

    start_index = next(
        (index for index, line in enumerate(lines) if line in CAFETERIA_NAMES),
        None,
    )
    if start_index is None:
        raise ValueError("식단 섹션 시작 지점을 찾지 못했습니다.")

    for index in range(start_index, len(lines)):
        if SECTION_END_MARKER in lines[index]:
            end_index = index
            break

    if end_index is None:
        raise ValueError("식단 섹션 종료 지점을 찾지 못했습니다.")

    return lines[start_index:end_index]


def split_cafeteria_blocks(section_lines: list[str]) -> list[tuple[str, list[str]]]:
    cafeterias: list[tuple[str, list[str]]] = []
    current_lines: list[str] | None = None

    for line in section_lines:
        if line in CAFETERIA_NAMES:
            current_lines = []
            cafeterias.append((line, current_lines))
            continue

        if current_lines is not None:
            current_lines.append(line)

    if not cafeterias:
        raise ValueError("식당 블록을 찾지 못했습니다.")

    return cafeterias


def build_menu_payloads(html: str, menu_date: str) -> list[Payload]:
    lines = html_to_lines(html)
    section_lines = extract_menu_section(lines)
    cafeteria_blocks = split_cafeteria_blocks(section_lines)

    payloads: list[Payload] = []
    for restaurant_name, block_lines in cafeteria_blocks:
        generalizer = CAFETERIA_GENERALIZERS.get(restaurant_name)
        if generalizer is None:
            raise ValueError(f"SNUDORM 식당 generalizer를 찾지 못했습니다: {restaurant_name}")
        metadata = CAFETERIA_METADATA.get(restaurant_name)
        if metadata is None:
            raise ValueError(f"SNUDORM 식당 metadata를 찾지 못했습니다: {restaurant_name}")

        meal_payloads = generalizer.generalize_cafeteria(block_lines)
        for meal_payload in meal_payloads:
            payloads.append({
                **metadata,
                "date": menu_date,
                **meal_payload,
            })

    return payloads


def record_failure(
    failures: list[tuple[str, Exception]],
    menu_date: str,
    stage: str,
    url: str,
    exc: Exception,
) -> None:
    failures.append((menu_date, exc))
    print(
        f"⚠️ [{menu_date}] 기숙사 식단 {stage} 실패 "
        f"({type(exc).__name__}, url={url}): {exc}",
        file=sys.stderr,
    )


def crawl_snudorm_menu(days_ahead: int = CRAWL_DAYS_AHEAD) -> tuple[list[Payload], list[tuple[str, Exception]]]:
    payloads: list[Payload] = []
    failures: list[tuple[str, Exception]] = []

    for menu_date in menu_dates(days_ahead):
        url = menu_url(menu_date)
        try:
            html = fetch_html(url)
        except requests.exceptions.RequestException as exc:
            record_failure(failures, menu_date, "fetch", url, exc)
            continue

        try:
            payloads.extend(build_menu_payloads(html, menu_date))
        except Exception as exc:
            record_failure(failures, menu_date, "parse", url, exc)

    return payloads, failures
