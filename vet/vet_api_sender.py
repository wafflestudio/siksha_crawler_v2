# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "beautifulsoup4",
#     "pytz",
# ]
# ///

import json
import re
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

import requests
import urllib3
from bs4 import BeautifulSoup
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))
from sync_state import plan_sync, payload_key, save_state

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

VET_URL = "https://vet.snu.ac.kr/cafe_menu/"

# ==========================================
# 1. 크롤링 및 파싱 로직 (휴무일 스킵 적용)
# ==========================================
class Fetcher:
    @staticmethod
    def fetch(url: str) -> BeautifulSoup:
        response = requests.get(url, timeout=10)
        return BeautifulSoup(response.text, "html.parser")

class DateParser:
    @staticmethod
    def parse_vet_date(date_str: str) -> datetime | None:
        pattern = r"^\d{1,2}\.\s\d{1,2}\(.\)$"
        if not re.match(pattern, date_str):
            return None

        reference_date = datetime.now() - timedelta(days=7)
        reference_year = reference_date.year
        cleaned_str = re.sub(r'\(.*\)', '', date_str).strip()
        
        try:
            dt_obj = datetime.strptime(f"{reference_year}. {cleaned_str}", "%Y. %m. %d")
            if dt_obj.date() < reference_date.date():
                dt_obj = dt_obj.replace(year=reference_year + 1)
            return dt_obj
        except ValueError:
            return None

class VetExtractor:
    def __init__(self, soup: BeautifulSoup) -> None:
        self.soup = soup

    def _extract_lunch(self) -> dict[str, str]:
        tbl = self.soup.select("table")
        if not tbl:
            return {}
        tbl = tbl[0]
        lunches = {}
        for tr in tbl.select("tr"):
            tds = tr.select("td")
            if len(tds) != 3:
                continue
            date = DateParser.parse_vet_date(tds[0].get_text().strip())
            if date is None:
                continue
            lunches[date.strftime("%Y-%m-%d")] = tds[1].get_text().strip()
        return lunches

    def _extract_dinner(self) -> str:
        all_elements = self.soup.find_all(string=re.compile("저녁메뉴"))
        if not all_elements:
            return ""
        text = all_elements[0].get_text()
        return text[text.find("저녁메뉴")+5:].strip()

    def extract(self) -> dict:
        lunches = self._extract_lunch()
        dinner = self._extract_dinner()
        
        result = {"수의대식당": {}}
        
        for date_str, lunch_menu in lunches.items():
            # 🚨 점심 메뉴에 '휴무'가 포함되어 있다면 해당 날짜 전체 스킵
            if "휴무" in lunch_menu:
                continue
                
            daily_meals = {
                "아침": [],
                "점심": [
                    {
                        "메뉴": [{"이름": lunch_menu, "가격": None}]
                    }
                ],
                "저녁": []
            }
            
            # 🚨 저녁 메뉴도 '휴무'가 아닐 때만 추가
            if dinner and "휴무" not in dinner:
                daily_meals["저녁"].append({
                    "메뉴": [{"이름": dinner, "가격": None}]
                })
                
            result["수의대식당"][date_str] = daily_meals
            
        return result

# ==========================================
# 2. API 전송 로직 (올바른 DTO 형식 & API Key 적용)
# ==========================================
def send_to_api(crawled_data: dict):
    api_url = "https://siksha-server-dev.wafflestudio.com/crawler/meals" 
    
    # 서버 환경변수에서 CRAWLER_API_KEY 읽어오기
    api_key = os.getenv("CRAWLER_API_KEY")

    if not api_key:
        print("🛑 오류: CRAWLER_API_KEY 환경 변수가 설정되지 않았습니다!")
        return
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key  
    }
    
    meal_type_map = {
        "아침": "BREAKFAST",
        "점심": "LUNCH",
        "저녁": "DINNER"
    }

    all_payloads = []

    for restaurant_name, dates in crawled_data.items():
        for date, meals_by_time in dates.items():
            for meal_time_kr, meal_groups in meals_by_time.items():
                meal_type_en = meal_type_map[meal_time_kr]
                dto_meals = []
                
                # 각 세트 메뉴를 서버 DTO(MealItem) 형식으로 변환
                for group in meal_groups:
                    menus = []
                    price = None
                    
                    for menu_item in group.get("메뉴", []):
                        name_text = menu_item["이름"]
                        if name_text and name_text != "없음":
                            menus.append(name_text)
                        
                        if price is None and menu_item.get("가격"):
                            price = menu_item["가격"]
                            
                    if menus:
                        dto_meals.append({
                            "price": price,
                            "noMeat": False,
                            "menus": menus
                        })
                
                # 최종 페이로드 구성
                payload = {
                    "restaurant": restaurant_name,
                    "date": date,
                    "type": meal_type_en,
                    "meals": dto_meals
                }
                all_payloads.append(payload)

    payloads_to_send, previous_state, new_state, stats = plan_sync("vet", all_payloads)
    print(
        f"📊 동기화 대상: 전체 {stats['current']}건 / 변경 {stats['changed']}건 / "
        f"삭제 {stats['deleted']}건 / 유지 {stats['unchanged']}건"
    )

    failed_keys = set()
    for payload in payloads_to_send:
        restaurant_name = payload["restaurant"]
        date = payload["date"]
        meal_type_en = payload["type"]

        print(f"🚀 [{restaurant_name} / {date} / {meal_type_en}] 데이터 전송 중...")

        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=5)
            response.raise_for_status()
            print(f"  ✅ 전송 성공: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"  ❌ 전송 실패: {e}")
            if e.response is not None:
                print(f"     응답 내용: {e.response.text}")
            failed_keys.add(payload_key(payload))

    # Save state only for successfully sent payloads; revert failed entries to
    # their previous values so they will be retried on the next run.
    committed_state = dict(new_state)
    for key in failed_keys:
        if key in previous_state:
            committed_state[key] = previous_state[key]
        else:
            committed_state.pop(key, None)
    save_state("vet", committed_state)

if __name__ == "__main__":
    print("🍽️ 수의대 식단 크롤링을 시작합니다...")
    
    try:
        soup = Fetcher.fetch(VET_URL)
        crawled_data = VetExtractor(soup).extract()
        
        print("📡 크롤링 완료! 백엔드 API로 전송을 시작합니다...")
        send_to_api(crawled_data)
        
        print("🎉 모든 작업이 완료되었습니다!")
        
    except Exception as e:
        print(f"🛑 오류 발생: {e}")