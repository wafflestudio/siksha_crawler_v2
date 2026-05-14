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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

VET_URL = "https://vet.snu.ac.kr/cafe_menu/"

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
            # 🚨 1. 점심 메뉴 텍스트에 '휴무'가 포함되어 있다면 해당 날짜는 통째로 스킵!
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
            
            # 🚨 2. 저녁 메뉴 역시 '휴무'가 아닐 때만 정상 추가
            if dinner and "휴무" not in dinner:
                daily_meals["저녁"].append({
                    "메뉴": [{"이름": dinner, "가격": None}]
                })
                
            result["수의대식당"][date_str] = daily_meals
            
        return result

# ==========================================
# 2. JSON 파일 저장 로직
# ==========================================
def save_to_json(crawled_data: dict, filename="vet_payload.json"):
    meal_type_map = {
        "아침": "BREAKFAST",
        "점심": "LUNCH",
        "저녁": "DINNER"
    }

    all_payloads = []

    for restaurant_name, dates in crawled_data.items():
        for date, meals_by_time in dates.items():
            for meal_time_kr, meal_groups in meals_by_time.items():
                if not meal_groups:
                    continue
                    
                meal_type_en = meal_type_map[meal_time_kr]
                dto_meals = []
                
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
                
                if not dto_meals:
                    continue
                
                payload = {
                    "restaurant": restaurant_name,
                    "date": date,
                    "type": meal_type_en,
                    "meals": dto_meals
                }
                all_payloads.append(payload)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_payloads, f, ensure_ascii=False, indent=2)
    print(f"📁 파싱된 데이터가 '{filename}'에 성공적으로 저장되었습니다!")

if __name__ == "__main__":
    print("🍽️ 수의대 식단 크롤링을 시작합니다...")
    
    try:
        soup = Fetcher.fetch(VET_URL)
        crawled_data = VetExtractor(soup).extract()
        
        print("📡 크롤링 완료! JSON 파일 변환을 시작합니다...")
        save_to_json(crawled_data)
        
        print("🎉 모든 작업이 완료되었습니다!")
        
    except Exception as e:
        print(f"🛑 오류 발생: {e}")