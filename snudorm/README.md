# SNUDORM Crawler Parsing Guide

이 문서는 `snudorm/crawl.py`가 기숙사 식단 페이지에서 HTML을 가져온 뒤, 식당별 generalizer에 데이터를 넘기기 전까지의 흐름을 설명한다.
아워홈/생협기숙사의 메뉴 정규화 규칙 자체는 `snudorm/generalizers/` 안에서 관리한다.

## Entry Point

```python
crawl_snudorm_menu(days_ahead: int = CRAWL_DAYS_AHEAD)
```

기본값은 `CRAWL_DAYS_AHEAD = 7`이다. `Asia/Seoul` 기준 오늘부터 7일 후까지, 총 8개 날짜를 순회한다.

각 날짜는 `menu_url(menu_date)`를 통해 다음 URL로 변환된다.

```text
https://snudorm.snu.ac.kr/foodmenu/?date=YYYY-MM-DD
```

## Parsing Flow

전체 흐름은 다음과 같다.

```text
crawl_snudorm_menu()
  -> menu_dates()
  -> menu_url(menu_date)
  -> fetch_html(url)
  -> build_menu_payloads(html, menu_date)
  -> html_to_lines(html)
  -> extract_menu_section(lines)
  -> split_cafeteria_blocks(section_lines)
  -> 식당별 generalizer.generalize_cafeteria(block_lines)
```

## HTML To Lines

SNUDORM은 SNUCO처럼 명확한 `menu-table` 구조를 바로 쓰지 않는다. 먼저 `TextExtractor(HTMLParser)`로 HTML 전체를 line list로 바꾼다.

`TextExtractor`는 다음 tag를 줄바꿈이 필요한 block tag로 본다.

```python
{
    "div", "p", "li", "ul", "ol", "section", "article",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
```

`br`도 줄바꿈으로 처리한다. 이후 `html_to_lines()`는 `\xa0`을 일반 공백으로 바꾸고, 공백을 하나로 압축한 뒤 빈 줄을 제거한다.

## Menu Section

`extract_menu_section()`은 전체 line list에서 식단 영역만 잘라낸다.

시작점:

```python
CAFETERIA_NAMES = (
    "아워홈(901동)",
    "생협기숙사(919동)",
)
```

위 식당명 중 하나가 처음 등장하는 line을 식단 시작점으로 본다.

종료점:

```text
개인정보처리방침
```

`개인정보처리방침`이 들어간 line 직전까지를 식단 section으로 본다.

## Cafeteria Blocks

`split_cafeteria_blocks()`는 잘라낸 식단 section을 다시 식당별 block으로 나눈다.

식당명 line을 만나면 새 block을 시작하고, 다음 식당명 line이 나오기 전까지의 line을 해당 식당의 `block_lines`로 모은다.

```python
[
    ("아워홈(901동)", [...]),
    ("생협기숙사(919동)", [...]),
]
```

## Data Passed To Generalizer

실제 `2026-05-15` SNUDORM 페이지를 파싱하면 `아워홈(901동)` block은 generalizer 직전에 다음처럼 만들어진다.

```python
restaurant_name = "아워홈(901동)"

block_lines = [
    "세미양식부페 : 5,000원",
    "단호박스프/조랭이떡국,치킨너겟,삶은계란*소금,토스트,씨리얼, 흰우유/두유,그린샐러드",
    "※운영시간 : 08:00~09:30",
    "목살김치찌개&수제깻잎어묵전 : 6,000원",
    "치즈오븐스파게티*마늘빵 : 6,000원",
    "(잇템)순살햄후라이 : 2,000원",
    "※운영시간 : 11:30~13:30",
    "새우볶음밥*짜장소스&제육땅콩강정 : 6,000원",
    "(잇템)소떡소떡 : 2,000원",
    "※운영시간 : 17:30~19:30",
]
```

같은 날짜의 `생협기숙사(919동)` block은 다음처럼 만들어진다.

```python
restaurant_name = "생협기숙사(919동)"

block_lines = [
    "냉모밀&미니알밥&새우튀김(#) : 6,000원",
    "※ 운영시간 : 11:30~13:30",
    "오리주물럭 : 6,500원",
    "※ 운영시간 : 17:30~19:00",
]
```

이후 `CAFETERIA_GENERALIZERS[restaurant_name]`에서 식당별 generalizer module을 찾고 다음처럼 호출한다.

```python
meal_payloads = generalizer.generalize_cafeteria(block_lines)
```

`crawl.py`는 source 식당명에 맞는 metadata와 `date`를 붙여 최종 payload list를 만든다.

```python
{
    **metadata,
    "date": menu_date,
    **meal_payload,
}
```

## Failure Handling

날짜별로 fetch와 parse 단계를 분리해 처리한다.

- `fetch_html()`에서 `requests.exceptions.RequestException`이 발생하면 해당 날짜를 fetch failure로 기록하고 다음 날짜로 넘어간다.
- section 시작점, section 종료점, 식당 block을 찾지 못하면 parse failure로 기록하고 다음 날짜로 넘어간다.
- generalizer 호출 중 예외가 발생해도 parse failure로 기록하고 다음 날짜로 넘어간다.
- 하나 이상의 failure가 있으면 `common.pipeline`에서 최종 exit code를 실패로 만든다.
