# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "beautifulsoup4",
#     "pytz",
# ]
# ///

from __future__ import annotations

import argparse
import json
import re
import sys
import os
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import requests
import urllib3
import pytz

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_URL = "https://snudorm.snu.ac.kr/foodmenu/"
SECTION_END_MARKER = "개인정보처리방침"
CAFETERIA_RE = re.compile(r"^(?P<name>.+?\(\d+동\))\s*(?P<rest>.*)$")
TIME_RE = re.compile(r"※\s*운영시간\s*:\s*(\d{2}:\d{2}~\d{2}:\d{2})")
PRICE_RE = re.compile(r"^(?P<menu>.+?)\s*:\s*(?P<price>[\d,]+원)$")
SECTION_MARKERS = ("식단 안내", "오늘의 식단")
HEADER_TOKENS = ("식당", "아침", "점심", "저녁")
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

    tz = pytz.timezone('Asia/Seoul')
    crawled_at = datetime.now(tz).strftime("%Y-%m-%d")
    result: dict[str, object] = {}

    for block in cafeteria_blocks:
        cafeteria = parse_cafeteria(block["name"], block["lines"]) 
        result[cafeteria["name"]] = {crawled_at: cafeteria["meals"]} 

    return result

def send_to_api(crawled_data: dict):
    api_url = "https://siksha-server-dev.wafflestudio.com/crawler/meals" 
    
    # 이 부분에 발급받은(사용가능한) 액세스 토큰(JWT)을 넣어야 서버로 보내지는 요청이 인증을 통과합니다.
    api_token = ""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}"
    }
    
    meal_type_map = {
        "아침": "BREAKFAST",
        "점심": "LUNCH",
        "저녁": "DINNER"
    }

    for restaurant_name, dates in crawled_data.items():
        for date, meals_by_time in dates.items():
            for meal_time_kr, meal_groups in meals_by_time.items():
                if not meal_groups:
                    continue
                    
                meal_type_en = meal_type_map[meal_time_kr]
                dto_meals = []
                
                for group in meal_groups:
                    # 🚨 수정된 로직: 독립된 메뉴를 분리해서 담을 객체 준비
                    current_dto_meal = {"price": None, "noMeat": False, "menus": []}
                    
                    for menu_item in group.get("메뉴", []):
                        name_text = menu_item["이름"]
                        item_price = menu_item.get("가격")
                        
                        if "(잇템)" in name_text:
                            name_text = name_text.replace("(잇템)", "").strip()
                        
                        # 새로운 가격이 등장했는데, 이미 담고 있던 메뉴에 가격이 있다면 => 이건 별도의 메뉴다! 끊어주자!
                        if item_price is not None and current_dto_meal["price"] is not None:
                            dto_meals.append(current_dto_meal)
                            current_dto_meal = {"price": item_price, "noMeat": False, "menus": []}
                            
                        # 처음 가격이 등장한 경우 세팅
                        if item_price is not None and current_dto_meal["price"] is None:
                            current_dto_meal["price"] = item_price
                            
                        current_dto_meal["menus"].append(name_text)
                        
                    # 마지막에 남은 메뉴 객체 털어넣기
                    if current_dto_meal["menus"]:
                        dto_meals.append(current_dto_meal)
                
                if not dto_meals:
                    continue
                    
                payload = {
                    "restaurant": restaurant_name,
                    "date": date,
                    "type": meal_type_en,
                    "meals": dto_meals
                }
                
                print(f"🚀 [{restaurant_name} / {date} / {meal_type_en}] 데이터 전송 중...")
                
                try:
                    response = requests.post(api_url, json=payload, headers=headers, timeout=5)
                    response.raise_for_status() 
                    print(f"  ✅ 전송 성공: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"  ❌ 전송 실패: {e}")
                    if e.response is not None:
                        print(f"     응답 내용: {e.response.text}")

def main() -> None:
    print("🍽️ 기숙사 식단 크롤링을 시작합니다...")
    
    try:
        html = fetch_html(DEFAULT_URL)
    except HTTPError as exc:
        print(f"HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc
    except URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        crawled_data = build_menu_json(DEFAULT_URL, html)
    except ValueError as exc:
        print(f"Parse error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("📡 크롤링 완료! 백엔드 API로 전송을 시작합니다...")
    send_to_api(crawled_data)
    
    print("🎉 모든 작업이 완료되었습니다!")

if __name__ == "__main__":
    main()