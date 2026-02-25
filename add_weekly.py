"""
주간 Weekly 페이지 관리.
- 입력한 날짜에 해당하는 주간 페이지가 없으면 생성
- 일간 relation에 Daily 페이지 연결
"""
import time
import logging
from datetime import date, timedelta
from notion_client import Client
from notion_config import get_client, WEEKLY_DS_ID, WEEKLY_DB_ID

log = logging.getLogger("notion_daily")


# ── 주차 계산 ──


def get_week_info(d: date) -> dict:
    """
    날짜로부터 주간 정보를 계산한다. (일요일~토요일 기준)

    Returns:
        {
            "year_short": "26",
            "year_full": "2026년",
            "week_num": 9,
            "start": date(2026, 3, 1),  # 일요일
            "end": date(2026, 3, 7),    # 토요일
            "title": "26년 9주 3.1-3.7",
        }
    """
    # 해당 날짜가 속한 주의 일요일 찾기 (weekday: 월=0 ... 일=6)
    days_since_sunday = (d.weekday() + 1) % 7
    sunday = d - timedelta(days=days_since_sunday)
    saturday = sunday + timedelta(days=6)

    # 주차 계산: 해당 년도 첫 번째 일요일부터 카운트
    year = sunday.year
    jan1 = date(year, 1, 1)
    # 첫 번째 일요일 찾기
    days_to_sunday = (6 - jan1.weekday()) % 7
    first_sunday = jan1 + timedelta(days=days_to_sunday)

    week_num = ((sunday - first_sunday).days // 7) + 1

    # 연초 1/1 이전의 일요일이 없는 경우 방어 (first_sunday가 1/2 이후)
    # → 해당 날짜의 일요일은 전년도에 속하므로 전년도 기준으로 계산됨
    if week_num < 1:
        raise ValueError(f"주차 계산 오류: {d} → week_num={week_num}")

    # 제목 생성 (연도 경계 시 "25년 52주 12.28-1.3" 형태)
    year_short = str(year)[2:]
    s = sunday
    e = saturday
    title = f"{year_short}년 {week_num}주 {s.month}.{s.day}-{e.month}.{e.day}"

    return {
        "year_short": year_short,
        "year_full": f"{year}년",
        "week_num": week_num,
        "start": sunday,
        "end": saturday,
        "title": title,
    }


# ── 주간 페이지 검색/생성 ──


def find_weekly_page(notion: Client, title: str) -> dict | None:
    """제목으로 주간 페이지를 검색한다."""
    resp = notion.data_sources.query(
        data_source_id=WEEKLY_DS_ID,
        filter={
            "property": "주간",
            "title": {"equals": title},
        },
    )
    results = resp.get("results", [])
    return results[0] if results else None


def create_weekly_page(
    notion: Client,
    title: str,
    year: str,
    daily_page_id: str,
) -> dict:
    """주간 Weekly 페이지를 새로 생성한다."""
    properties = {
        "주간": {"title": [{"text": {"content": title}}]},
        "년도": {"select": {"name": year}},
        "일간": {"relation": [{"id": daily_page_id}]},
    }

    new_page = notion.pages.create(
        parent={"database_id": WEEKLY_DB_ID},
        properties=properties,
    )
    return new_page


def add_daily_to_weekly(
    notion: Client,
    weekly_page_id: str,
    daily_page_id: str,
) -> dict:
    """기존 주간 페이지의 '일간' relation에 Daily 페이지를 추가한다."""
    # 기존 relation 읽기
    page = notion.pages.retrieve(page_id=weekly_page_id)
    existing = page.get("properties", {}).get("일간", {}).get("relation", [])
    existing_ids = [r["id"] for r in existing]

    # 이미 연결되어 있으면 스킵
    if daily_page_id in existing_ids:
        log.info(f"  이미 연결되어 있음: {daily_page_id}")
        return page

    # 추가
    all_ids = existing_ids + [daily_page_id]
    return notion.pages.update(
        page_id=weekly_page_id,
        properties={
            "일간": {"relation": [{"id": pid} for pid in all_ids]},
        },
    )


# ── 메인 함수 ──


def ensure_weekly(notion: Client, daily_date: str, daily_page_id: str) -> tuple[dict, bool]:
    """
    Daily 날짜에 해당하는 주간 페이지를 찾거나 생성하고, 일간 relation을 연결한다.

    Args:
        daily_date: "2026-03-01"
        daily_page_id: Daily 페이지 ID

    Returns:
        (주간 페이지 dict, is_new)
    """
    d = date.fromisoformat(daily_date)
    week = get_week_info(d)

    log.info(f"  날짜: {daily_date} → {week['title']}")

    # 연도 경계 알림 (예: 2026-01-01 → 25년 52주)
    if d.year != week["start"].year:
        log.info(f"  연도 경계: 입력 {d.year}년, 주간 {week['year_full']}")

    # 검색
    existing = find_weekly_page(notion, week["title"])

    if existing:
        log.info(f"  기존 주간 페이지 발견: {existing['id']}")
        add_daily_to_weekly(notion, existing["id"], daily_page_id)
        log.info(f"  일간 relation 연결 완료")
        return existing, False
    else:
        log.info(f"  주간 페이지 생성 중: {week['title']}")
        new_page = create_weekly_page(
            notion, week["title"], week["year_full"], daily_page_id
        )
        log.info(f"  생성 완료: {new_page['id']}")
        log.info(f"  URL: {new_page.get('url', '')}")
        return new_page, True


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("사용법: python add_weekly.py <daily_page_id> <날짜 YYYY-MM-DD>")
        sys.exit(1)

    daily_page_id = sys.argv[1]
    daily_date = sys.argv[2]

    notion = get_client()
    log.info("=== 주간 Weekly 페이지 처리 ===\n")
    weekly_page, _ = ensure_weekly(notion, daily_date, daily_page_id)
    log.info("\n완료!")
