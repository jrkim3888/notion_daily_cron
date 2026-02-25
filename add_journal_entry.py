"""
Journal Overall 페이지에 날짜 토글 + synced_block 참조를 추가하는 스크립트.
add_daily.py의 create_daily_page()가 반환하는 synced_ids를 사용한다.
"""
import time
import logging
from notion_client import Client
from notion_config import get_client, JOURNAL_PAGE_ID

log = logging.getLogger("notion_daily")


def get_blocks(notion: Client, block_id: str) -> list:
    blocks = []
    start_cursor = None
    while True:
        kwargs = {"block_id": block_id}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        resp = notion.blocks.children.list(**kwargs)
        blocks.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        start_cursor = resp.get("next_cursor")
    return blocks


def get_text(block: dict) -> str:
    btype = block.get("type", "")
    rich_text = block.get(btype, {}).get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in rich_text)


def find_synced_ids_from_page(notion: Client, daily_page_id: str) -> dict:
    """이미 생성된 Daily 페이지에서 synced_block 원본 ID를 찾는다."""
    blocks = get_blocks(notion, daily_page_id)
    synced_ids = {}
    for b in blocks:
        if b.get("type") == "synced_block" and b.get("synced_block", {}).get("synced_from") is None:
            children = get_blocks(notion, b["id"])
            for c in children:
                text = get_text(c)
                if "기록 - 개인" in text:
                    synced_ids["기록 - 개인"] = b["id"]
                elif "기록 - 업무" in text:
                    synced_ids["기록 - 업무"] = b["id"]
    return synced_ids


def add_to_journal(
    notion: Client,
    year: str,
    month: str,
    date_title: str,
    synced_block_ids: dict,
) -> bool:
    """
    Journal Overall 페이지에 날짜 토글 + synced_block 참조를 추가한다.

    Args:
        year: "2026년"
        month: "2026년 3월"
        date_title: "2026년 3월 1일 (일)"
        synced_block_ids: {"기록 - 개인": id, "기록 - 업무": id}

    Returns:
        True면 신규 추가, False면 이미 존재하여 스킵
    """
    # 1) 년도 토글 찾기
    top_blocks = get_blocks(notion, JOURNAL_PAGE_ID)
    year_block = None
    for b in top_blocks:
        if b.get("type") == "heading_1" and get_text(b) == year:
            year_block = b
            break

    if not year_block:
        log.info(f"  년도 토글 '{year}' 생성 중...")
        resp = notion.blocks.children.append(
            block_id=JOURNAL_PAGE_ID,
            children=[{
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": year}}],
                    "is_toggleable": True,
                },
            }],
        )
        year_block = resp["results"][0]
        time.sleep(0.35)

    year_id = year_block["id"]

    # 2) 월 토글 찾기
    month_blocks = get_blocks(notion, year_id)
    month_block = None
    for b in month_blocks:
        if b.get("type") == "heading_2" and get_text(b) == month:
            month_block = b
            break

    if not month_block:
        log.info(f"  월 토글 '{month}' 생성 중...")
        resp = notion.blocks.children.append(
            block_id=year_id,
            children=[{
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": month}}],
                    "is_toggleable": True,
                },
            }],
            **{"position": {"type": "start"}},
        )
        month_block = resp["results"][0]
        time.sleep(0.35)

    month_id = month_block["id"]

    # 3) 날짜 토글 중복 체크 (요일 제외, "2026년 3월 1일"까지만 비교)
    date_part = date_title.rsplit(" ", 1)[0]  # "2026년 3월 1일 (일)" → "2026년 3월 1일"
    month_children = get_blocks(notion, month_id)
    for b in month_children:
        if b.get("type") == "heading_3" and date_part in get_text(b):
            log.info(f"  날짜 토글 '{date_title}' 이미 존재, 스킵")
            return False

    # 날짜 토글 + synced_block 참조 생성
    log.info(f"  날짜 토글 '{date_title}' + 동기화 블록 추가 중...")
    resp = notion.blocks.children.append(
        block_id=month_id,
        children=[{
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": date_title}}],
                "is_toggleable": True,
            },
        }],
        **{"position": {"type": "start"}},
    )
    date_heading_id = resp["results"][0]["id"]
    time.sleep(0.35)

    synced_refs = []
    for label in ["기록 - 개인", "기록 - 업무"]:
        if label in synced_block_ids:
            synced_refs.append({
                "type": "synced_block",
                "synced_block": {
                    "synced_from": {
                        "block_id": synced_block_ids[label],
                    },
                },
            })

    if synced_refs:
        notion.blocks.children.append(block_id=date_heading_id, children=synced_refs)

    log.info("  Journal Overall 추가 완료!")
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("사용법: python add_journal_entry.py <daily_page_id> [날짜 YYYY-MM-DD]")
        sys.exit(1)

    daily_page_id = sys.argv[1]
    target_date = sys.argv[2] if len(sys.argv) > 2 else "2026-03-01"

    from datetime import date as dt
    d = dt.fromisoformat(target_date)
    day_names = ["월", "화", "수", "목", "금", "토", "일"]

    notion = get_client()
    log.info("=== Daily 페이지에서 synced_block ID 검색 ===\n")
    synced_ids = find_synced_ids_from_page(notion, daily_page_id)
    log.info(f"  synced_ids: {synced_ids}\n")

    if len(synced_ids) < 2:
        log.info("ERROR: synced_block을 찾을 수 없습니다. add_daily.py로 먼저 페이지를 생성하세요.")
    else:
        log.info("=== Journal Overall 추가 ===\n")
        add_to_journal(
            notion,
            year=f"{d.year}년",
            month=f"{d.year}년 {d.month}월",
            date_title=f"{d.year}년 {d.month}월 {d.day}일 ({day_names[d.weekday()]})",
            synced_block_ids=synced_ids,
        )
        log.info("\n완료!")
