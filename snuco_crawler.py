# 학생 식당 및 교직원 식당 (생협 식당 크롤러 코드)

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
from datetime import datetime
import requests
import urllib3
from bs4 import BeautifulSoup
import pytz

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def clean_menu_name(text):
    text = re.sub(r'[※►].*', '', text)
    text = re.sub(r'[①②③④⑤]', '', text)
    text = text.replace('(잇템)', '').replace('[#]', '').replace('(#)', '')
    text = text.replace('< 채식뷔페 >:', '').replace('<주문식 메뉴>', '')
    text = re.sub(r'\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2}', '', text)
    return text.strip()

def is_valid_meal(text):
    # 자하연 3층의 뷔페 안내 문구 등을 날리기 위해 필터링 키워드 대폭 추가
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
        restaurant_name = re.sub(r'\(.*?\)', '', raw_restaurant_name).strip()
        
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
            
            # 뷔페 모드를 위한 상태 변수
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
                    price_match = re.search(r'(?<!\d)([1-9]\d*00)(?!\d)', menu_text)

                if price_match:
                    price = int(re.sub(r'\D', '', price_match.group(1)))
                    menu_text = menu_text.replace(price_match.group(0), "").strip()
                
                clean_for_corner = menu_text.strip()
                
                # 코너 조건: <이름> 형태이거나 특정 예외(+세미뷔페)인 경우
                is_corner_format = (clean_for_corner.startswith('<') and clean_for_corner.endswith('>')) or clean_for_corner == '+세미뷔페'
                
                if is_corner_format:
                    corner_name = clean_for_corner.replace('<', '').replace('>', '').replace('+', '').strip()
                    corner_name_no_space = corner_name.replace(' ', '')
                    
                    # 1. 가짜 코너 처리 (공대간이식당의 메뉴, 사이드)
                    if corner_name_no_space in ["메뉴", "사이드"]:
                        continue # 코너를 무시하고 기존 배열에 계속 이어붙입니다.
                        
                    # 2. 진짜 코너 시작 (이전 그룹 닫기)
                    # 뷔페 모드였다면 뷔페 아이템들을 하나의 메뉴로 묶어서 추가
                    if is_buffet_mode and buffet_items:
                        current_menus.append({
                            "이름": buffet_items,
                            "가격": buffet_price
                        })
                        buffet_items = []
                        is_buffet_mode = False
                        
                    # 이전 메뉴들이 남아있다면 그룹화하여 저장
                    if current_menus:
                        group = {}
                        if current_corner:
                            group["코너"] = current_corner
                        group["메뉴"] = current_menus
                        meal_groups.append(group)
                        current_menus = []
                        
                    # 새 코너 지정
                    current_corner = corner_name
                    
                    # 3. 뷔페/셀프코너 판별
                    if "뷔페" in corner_name_no_space or "셀프코너" in corner_name_no_space:
                        is_buffet_mode = True
                        buffet_price = price # 뷔페 가격 기억
                        
                    continue
                    
                # 일반 메뉴 이름 클리닝
                menu_text = clean_menu_name(menu_text)
                menu_text = re.sub(r'[:\-ㅁ\(\)]+$', '', menu_text).strip()
                
                if menu_text:
                    # 뷔페 모드일 때는 이름만 배열에 모아둡니다.
                    if is_buffet_mode:
                        buffet_items.append(menu_text)
                    else:
                        current_menus.append({
                            "이름": menu_text,
                            "가격": price
                        })
                        
            # 셀(시간대)의 끝에 도달했을 때 남은 데이터들 처리
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

if __name__ == "__main__":
    crawled_data = crawl_snuco_menu()
    print(json.dumps(crawled_data, ensure_ascii=False, indent=2))