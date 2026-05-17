import json
import os
import sys
from pathlib import Path

import requests

from .types import CrawlFailure, CrawlFunction


API_URL = os.getenv("CRAWLER_API_URL", "https://siksha-server-dev.wafflestudio.com/crawler/meals")


def post_payloads(payloads: list[dict], source: str) -> None:
    api_key = os.getenv("CRAWLER_API_KEY")
    if not api_key:
        raise RuntimeError("CRAWLER_API_KEY 환경 변수가 설정되지 않았습니다.")

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    failures: list[tuple[dict, Exception]] = []

    for payload in payloads:
        restaurant_name = payload["restaurant"]
        date = payload["date"]
        meal_type = payload["type"]

        print(f"🚀 [{restaurant_name} / {date} / {meal_type}] 데이터 전송 중...")

        try:
            response = requests.post(API_URL, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            print(f"  ✅ 전송 성공: {response.status_code}")
        except requests.exceptions.RequestException as exc:
            failures.append((payload, exc))
            print(f"  ❌ 전송 실패: {exc}")
            if exc.response is not None:
                print(f"     응답 내용: {exc.response.text}")

    if failures:
        raise RuntimeError(f"{source} API 전송 실패: {len(failures)}건")


def save_payloads(payloads: list[dict], filename: str) -> None:
    path = Path(filename)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payloads, f, ensure_ascii=False, indent=2)
    print(f"📁 파싱된 데이터가 '{filename}'에 성공적으로 저장되었습니다!")


def report_crawl_failures(source: str, failures: list[CrawlFailure]) -> None:
    failed_targets = ", ".join(target for target, _ in failures)
    print(f"🛑 {source} 크롤링 실패 감지: {failed_targets}", file=sys.stderr)


def run_api(source: str, crawl_fn: CrawlFunction) -> None:
    print(f"🍽️ {source} 식단 크롤링을 시작합니다...")
    payloads, crawl_failures = crawl_fn()

    print("📡 크롤링 완료! 백엔드 API로 전송을 시작합니다...")
    post_payloads(payloads, source)

    if crawl_failures:
        report_crawl_failures(source, crawl_failures)
        raise SystemExit(1)

    print("🎉 모든 작업이 완료되었습니다!")


def run_json(source: str, crawl_fn: CrawlFunction, output_file: str) -> None:
    print(f"🍽️ {source} 식단 크롤링을 시작합니다...")
    payloads, crawl_failures = crawl_fn()

    print("📡 크롤링 완료! JSON 파일 변환을 시작합니다...")
    save_payloads(payloads, output_file)

    if crawl_failures:
        report_crawl_failures(source, crawl_failures)
        raise SystemExit(1)

    print("🎉 모든 작업이 완료되었습니다!")
