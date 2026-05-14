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
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any
import requests
import urllib3
from bs4 import BeautifulSoup
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. API 페이로드 객체 정의 (Data Object)
# ==========================================
@dataclass
class DailyMenuPayload:
    restaurant_name: str
    date: str
    breakfast: List[Dict[str, Any]]
    lunch: List[Dict[str, Any]]
    dinner: List[Dict[str, Any]]

# ==========================================
# 2. 크롤링 및 파싱 로직
# ==========================================
def clean_menu_name(text):
    text = re.sub(r'[※►].*', '', text)
    text = re.sub(r'[①②③④⑤]', '', text)
    text = text.replace('(잇템)', '').replace('[#]', '').replace('(#)', '')
    text = text.replace('< 채식뷔페 >:', '').replace('<주문식 메뉴>', '')
    text = re.sub(r'\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2}', '', text)
    return text.strip()

def is_valid_meal(text):
    exclude_keywords = [
        "휴무", "휴점", "폐점", "휴업", "휴관", 
        "운영", "시간", "제공", "배식시간", "혼잡시간", 
        "브레이크", "break", "오전", "오후", "평일", "토요일", 
        "TakeOut", "TAKE", "결제", "문의", "학기중", "하계방학",
        "대학원생", "준비수량", "특성상", "조기품절", "가능성이", "양해"
    ]
    text_lower = text.lower()
    for keyword in exclude_keywords:
        if keyword.lower() in text_lower:
            return False
    return True

def crawl_snuco_menu():
    url = "https://snuco.snu.ac.kr/foodmenu/"
    tz = pytz.timezone('Asia/Seoul')
    today = datetime.now(tz).strftime("%Y-%m-%d")
    
    response = requests.get(url, params={"date": today}, verify=False)
    soup = BeautifulSoup(response.text, "html.parser")
    
    result = {}
    table = soup.find("table", class_="menu-table")
    
    if not table or not table.tbody:
        return result
        
    trs = table.tbody.find_all("tr", recursive=False)
    
    for tr in trs:
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
            
        raw_restaurant_name = tds[0].text.strip()
        restaurant_name = re.sub(r'\(.*?\)', '', raw_restaurant_name).replace('*', '').strip()
        
        # 🚨 기숙사식당 및 버거운버거 제외
        if restaurant_name in ["기숙사식당", "버거운버거"]:
            continue
        
        if restaurant_name not in result:
            result[restaurant_name] = {today: {"아침": [], "점심": [], "저녁": []}}
            
        for td in tds[1:]:
            meal_type_class = td.get("class", [""])[0]
            
            meal_time = None
            if "breakfast" in meal_type_class:
                meal_time = "아침"
            elif "lunch" in meal_type_class:
                meal_time = "점심"
            elif "dinner" in meal_type_class:
                meal_time = "저녁"
                
            if not meal_time:
                continue
                
            raw_menus = td.get_text(separator="\n").split("\n")
            
            meal_groups = []       
            current_corner = None  
            current_menus = []     
            
            is_buffet_mode = False
            buffet_price = None
            buffet_items = []
            
            for raw_menu in raw_menus:
                menu_text = raw_menu.strip()
                if not menu_text or menu_text == "\xa0":
                    continue
                    
                if not is_valid_meal(menu_text):
                    continue
                    
                price = None
                
                price_match = re.search(r'([1-9]\d{0,2}(?:[,.]\d{3})*|\d+)\s*원', menu_text)
                if not price_match:
                    price_match = re.search(r'(?<![\d,])([1-9]\d{0,2},\d{3}|[1-9]\d{2,}00)(?![\d,])', menu_text)

                if price_match:
                    price_str = price_match.group(1)
                    price = int(re.sub(r'\D', '', price_str))
                    menu_text = menu_text.replace(price_match.group(0), "").strip()
                
                clean_for_corner = menu_text.strip()
                
                is_corner_format = (clean_for_corner.startswith('<') and clean_for_corner.endswith('>')) or clean_for_corner == '+세미뷔페'
                
                if is_corner_format:
                    corner_name = clean_for_corner.replace('<', '').replace('>', '').replace('+', '').strip()
                    corner_name_no_space = corner_name.replace(' ', '')
                    
                    if corner_name_no_space in ["메뉴", "사이드"]:
                        continue 
                        
                    if is_buffet_mode and buffet_items:
                        current_menus.append({
                            "이름": buffet_items,
                            "가격": buffet_price
                        })
                        buffet_items = []
                        is_buffet_mode = False
                        
                    if current_menus:
                        group = {}
                        if current_corner:
                            group["코너"] = current_corner
                        group["메뉴"] = current_menus
                        meal_groups.append(group)
                        current_menus = []
                        
                    current_corner = corner_name
                    
                    if "뷔페" in corner_name_no_space or "셀프코너" in corner_name_no_space:
                        is_buffet_mode = True
                        buffet_price = price 
                        
                    continue
                    
                menu_text = clean_menu_name(menu_text)
                menu_text = re.sub(r'[:\-ㅁ\/]+$', '', menu_text).strip()
                
                if menu_text:
                    if is_buffet_mode:
                        buffet_items.append(menu_text)
                    else:
                        current_menus.append({
                            "이름": menu_text,
                            "가격": price
                        })
                        
            if is_buffet_mode and buffet_items:
                current_menus.append({
                    "이름": buffet_items,
                    "가격": buffet_price
                })
                
            if current_menus:
                group = {}
                if current_corner:
                    group["코너"] = current_corner
                group["메뉴"] = current_menus
                meal_groups.append(group)
                
            result[restaurant_name][today][meal_time] = meal_groups
                
    return result

# ==========================================
# 3. JSON 파일 저장 로직 (맞춤형 문자열 분리/교정 적용)
# ==========================================
def save_to_json(crawled_data: dict, filename="snuco_payload.json"):
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
                    current_dto_meal = {"price": None, "noMeat": False, "menus": []}
                    
                    for menu_item in group.get("메뉴", []):
                        names = menu_item["이름"] if isinstance(menu_item["이름"], list) else [menu_item["이름"]]
                        item_price = menu_item.get("가격")
                        
                        parsed_names_all = []
                        for name_text in names:
                            # 🚨 1. 공대간이식당 호구세트 가격 하드코딩 복구
                            if "호구세트" in name_text:
                                name_text = "호구세트"
                                item_price = 8300
                            
                            # 🚨 2. 예술계식당의 <A코너> 같은 불필요한 태그 제거
                            name_text = re.sub(r'<[A-Za-z가-힣0-9]+코너>', '', name_text)
                            
                            # 🚨 3. 220동식당의 불필요한 "세트" 꼬리 자르기
                            name_text = name_text.replace("제육한접시 세트", "제육한접시").replace("제육한접시세트", "제육한접시")
                            name_text = name_text.replace("고기한접시 세트", "고기한접시").replace("고기한접시세트", "고기한접시")
                            
                            # 🚨 4. &, 콤마(,), +, _ 를 기준으로 메뉴들을 모두 예쁘게 쪼개기
                            parsed = [n.strip() for n in re.split(r'[&,\+_]', name_text) if n.strip()]
                            parsed_names_all.extend(parsed)
                        
                        if item_price is not None and current_dto_meal["price"] is not None:
                            dto_meals.append(current_dto_meal)
                            current_dto_meal = {"price": item_price, "noMeat": False, "menus": []}
                        
                        if item_price is not None and current_dto_meal["price"] is None:
                            current_dto_meal["price"] = item_price
                            
                        # 쪼개진 모든 배열을 추가
                        current_dto_meal["menus"].extend(parsed_names_all)
                        
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
                all_payloads.append(payload)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_payloads, f, ensure_ascii=False, indent=2)
    print(f"📁 파싱된 데이터가 '{filename}'에 성공적으로 저장되었습니다!")

if __name__ == "__main__":
    print("🍽️ 식단 크롤링을 시작합니다...")
    crawled_data = crawl_snuco_menu()
    
    print("📡 크롤링 완료! JSON 파일 변환을 시작합니다...")
    save_to_json(crawled_data)
    
    print("🎉 모든 작업이 완료되었습니다!")