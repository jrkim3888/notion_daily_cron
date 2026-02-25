"""
월간 Monthly 페이지 관리.
- 해당 월 페이지가 없으면 생성
- 주간 relation에 Weekly 페이지 연결
"""
import logging
from datetime import date
from notion_client import Client
from notion_config import get_client, MONTHLY_DS_ID, MONTHLY_DB_ID

log = logging.getLogger("notion_daily")


def get_month_info(d: date) -> dict:
    """날짜에서 월간 정보를 추출한다."""
    return {
        "title": f"{d.year}.{d.month:02d}월",
        "year": f"{d.year}년",
    }


def find_monthly_page(notion: Client, title: str) -> dict | None:
    """제목으로 월간 페이지를 검색한다."""
    resp = notion.data_sources.query(
        data_source_id=MONTHLY_DS_ID,
        filter={
            "property": "월간",
            "title": {"equals": title},
        },
    )
    results = resp.get("results", [])
    return results[0] if results else None


def create_monthly_page(
    notion: Client,
    title: str,
    year: str,
    weekly_page_id: str,
) -> dict:
    """월간 Monthly 페이지를 새로 생성한다."""
    properties = {
        "월간": {"title": [{"text": {"content": title}}]},
        "년도": {"select": {"name": year}},
        "주간": {"relation": [{"id": weekly_page_id}]},
    }
    return notion.pages.create(
        parent={"database_id": MONTHLY_DB_ID},
        properties=properties,
    )


def add_weekly_to_monthly(
    notion: Client,
    monthly_page_id: str,
    weekly_page_id: str,
) -> dict:
    """기존 월간 페이지의 '주간' relation에 Weekly 페이지를 추가한다."""
    page = notion.pages.retrieve(page_id=monthly_page_id)
    existing = page.get("properties", {}).get("주간", {}).get("relation", [])
    existing_ids = [r["id"] for r in existing]

    if weekly_page_id in existing_ids:
        log.info(f"  이미 연결되어 있음: {weekly_page_id}")
        return page

    all_ids = existing_ids + [weekly_page_id]
    return notion.pages.update(
        page_id=monthly_page_id,
        properties={
            "주간": {"relation": [{"id": pid} for pid in all_ids]},
        },
    )


def ensure_monthly(notion: Client, daily_date: str, weekly_page_id: str) -> tuple[dict, bool]:
    """
    Daily 날짜에 해당하는 월간 페이지를 찾거나 생성하고, 주간 relation을 연결한다.

    Args:
        daily_date: "2026-03-01"
        weekly_page_id: Weekly 페이지 ID

    Returns:
        (월간 페이지 dict, is_new)
    """
    d = date.fromisoformat(daily_date)
    month = get_month_info(d)

    log.info(f"  날짜: {daily_date} → {month['title']}")

    existing = find_monthly_page(notion, month["title"])

    if existing:
        log.info(f"  기존 월간 페이지 발견: {existing['id']}")
        add_weekly_to_monthly(notion, existing["id"], weekly_page_id)
        log.info(f"  주간 relation 연결 완료")
        return existing, False
    else:
        log.info(f"  월간 페이지 생성 중: {month['title']}")
        new_page = create_monthly_page(
            notion, month["title"], month["year"], weekly_page_id
        )
        log.info(f"  생성 완료: {new_page['id']}")
        log.info(f"  URL: {new_page.get('url', '')}")
        return new_page, True


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("사용법: python add_monthly.py <weekly_page_id> <날짜 YYYY-MM-DD>")
        sys.exit(1)

    weekly_page_id = sys.argv[1]
    daily_date = sys.argv[2]

    notion = get_client()
    log.info("=== 월간 Monthly 페이지 처리 ===\n")
    monthly_page, _ = ensure_monthly(notion, daily_date, weekly_page_id)
    log.info("\n완료!")
