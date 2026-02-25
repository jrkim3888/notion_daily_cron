"""일간 Daily 데이터베이스에 새 페이지를 추가하고 템플릿을 적용하는 스크립트."""
import time
import logging
from notion_client import Client
from notion_config import get_client, DAILY_DS_ID, DAILY_DB_ID, TEMPLATE_PAGE_ID

log = logging.getLogger("notion_daily")

# synced_block으로 감쌀 heading 이름
_SYNCED_HEADINGS = {"기록 - 개인", "기록 - 업무"}

# API로 생성 불가능한 블록 타입
_SKIP_TYPES = {"unsupported", "child_page", "child_database", "link_preview"}


# ── 블록 읽기 (재귀) ──


def read_blocks(notion: Client, block_id: str) -> list:
    """블록의 자식들을 재귀적으로 읽는다."""
    blocks = []
    start_cursor = None
    while True:
        kwargs = {"block_id": block_id}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        resp = notion.blocks.children.list(**kwargs)
        for block in resp.get("results", []):
            if block.get("has_children"):
                block["_children"] = read_blocks(notion, block["id"])
            blocks.append(block)
        if not resp.get("has_more"):
            break
        start_cursor = resp.get("next_cursor")
    return blocks


def get_text(block: dict) -> str:
    btype = block.get("type", "")
    rich_text = block.get(btype, {}).get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in rich_text)


# ── 블록 정리 (복사용) ──


def clean_block(block: dict) -> dict | None:
    """블록에서 메타데이터를 제거하여 생성 가능한 형태로 만든다."""
    btype = block.get("type")
    if not btype or btype in _SKIP_TYPES:
        return None

    cleaned = {"type": btype}
    type_data = block.get(btype)
    if type_data is None:
        return None

    # type_data 복사 (children 키 제외)
    cleaned[btype] = {k: v for k, v in type_data.items() if k != "children"}
    return cleaned


# ── 템플릿 복사 (synced_block 감싸기 포함) ──


def copy_template_with_synced(
    notion: Client, template_page_id: str, target_page_id: str
) -> dict:
    """
    템플릿 블록을 복사하되, '기록-개인/업무' heading_3는 synced_block으로 감싼다.
    rich_text(색상 등)를 그대로 유지한다.

    Returns:
        {"기록 - 개인": synced_block_id, "기록 - 업무": synced_block_id}
    """
    template_blocks = read_blocks(notion, template_page_id)

    # 1단계: 최상위 블록 목록 구성 (heading_3 → synced_block 변환)
    blocks_to_create = []
    # 각 블록에 대해 (synced_heading_name or None, children) 기록
    block_meta = []

    for block in template_blocks:
        btype = block.get("type")
        if not btype or btype in _SKIP_TYPES:
            continue

        text = get_text(block)
        children = block.get("_children", [])

        if btype == "heading_3" and text in _SYNCED_HEADINGS:
            # heading_3의 원본 rich_text와 속성을 그대로 사용
            heading_data = block.get("heading_3", {})
            original_rich_text = heading_data.get("rich_text", [])
            # rich_text에서 href만 정리 (복사 시 불필요한 링크 제거)
            clean_rich_text = []
            for rt in original_rich_text:
                clean_rt = {
                    "type": rt.get("type", "text"),
                    "text": rt.get("text", {}),
                }
                if "annotations" in rt:
                    clean_rt["annotations"] = rt["annotations"]
                clean_rich_text.append(clean_rt)

            blocks_to_create.append({
                "type": "synced_block",
                "synced_block": {
                    "synced_from": None,
                    "children": [{
                        "type": "heading_3",
                        "heading_3": {
                            "rich_text": clean_rich_text,
                            "is_toggleable": True,
                        },
                    }],
                },
            })
            block_meta.append((text, children))
        else:
            cleaned = clean_block(block)
            if cleaned:
                blocks_to_create.append(cleaned)
                block_meta.append((None, children))

    # 2단계: 블록 일괄 생성
    log.info(f"  블록 {len(blocks_to_create)}개 생성 중...")
    created = []
    for i in range(0, len(blocks_to_create), 100):
        batch = blocks_to_create[i : i + 100]
        resp = notion.blocks.children.append(block_id=target_page_id, children=batch)
        created.extend(resp.get("results", []))
        if i + 100 < len(blocks_to_create):
            time.sleep(0.35)

    # 3단계: synced_block ID 수집 + heading children 복원
    synced_ids = {}
    for idx, (label, children) in enumerate(block_meta):
        if idx >= len(created):
            break

        block = created[idx]

        if label:
            # synced_block → 내부 heading_3 찾아서 children 추가
            synced_ids[label] = block["id"]
            if children:
                time.sleep(0.35)
                inner = notion.blocks.children.list(block_id=block["id"])
                heading_id = inner["results"][0]["id"] if inner["results"] else None
                if heading_id:
                    child_blocks = []
                    for c in children:
                        cleaned = clean_block(c)
                        if cleaned:
                            child_blocks.append(cleaned)
                    if child_blocks:
                        notion.blocks.children.append(
                            block_id=heading_id, children=child_blocks
                        )
        elif children:
            # 일반 블록의 자식 재귀 처리
            time.sleep(0.35)
            _write_children_recursive(notion, block["id"], children)

    return synced_ids


def _write_children_recursive(notion: Client, parent_id: str, blocks: list):
    """자식 블록을 재귀적으로 추가한다."""
    to_create = []
    children_map = []
    for block in blocks:
        cleaned = clean_block(block)
        if cleaned:
            to_create.append(cleaned)
            children_map.append(block.get("_children", []))

    if not to_create:
        return

    resp = notion.blocks.children.append(block_id=parent_id, children=to_create)
    created = resp.get("results", [])

    for idx, children in enumerate(children_map):
        if children and idx < len(created):
            time.sleep(0.35)
            _write_children_recursive(notion, created[idx]["id"], children)


# ── 페이지 생성 ──


def find_daily_page(notion: Client, title: str) -> dict | None:
    """제목으로 Daily 페이지를 검색한다. 날짜 부분(YYYY-MM-DD)만으로 매칭."""
    date_part = title.split(" ")[0]  # "2026-02-25 (화)" → "2026-02-25"
    resp = notion.data_sources.query(
        data_source_id=DAILY_DS_ID,
        filter={
            "property": "일간",
            "title": {"contains": date_part},
        },
    )
    results = resp.get("results", [])
    return results[0] if results else None


def create_daily_page(
    notion: Client,
    title: str,
    date: str,
    year: str = "2026년",
    template_page_id: str | None = None,
) -> tuple[dict, dict, bool]:
    """
    일간 Daily DB에 새 페이지를 생성한다. 이미 존재하면 기존 페이지를 반환.

    Returns:
        (page_dict, synced_ids, is_new)
        synced_ids: {"기록 - 개인": block_id, "기록 - 업무": block_id} (템플릿 사용 시)
        is_new: True면 신규 생성, False면 기존 페이지
    """
    # 중복 체크
    existing = find_daily_page(notion, title)
    if existing:
        log.info(f"이미 존재하는 페이지: {existing['id']}")
        from add_journal_entry import find_synced_ids_from_page
        synced_ids = find_synced_ids_from_page(notion, existing["id"])
        return existing, synced_ids, False

    properties = {
        "일간": {"title": [{"text": {"content": title}}]},
        "년도": {"select": {"name": year}},
        "날짜": {"date": {"start": date}},
    }

    new_page = notion.pages.create(
        parent={"database_id": DAILY_DB_ID},
        properties=properties,
    )
    log.info(f"페이지 생성 완료: {new_page['id']}")
    log.info(f"URL: {new_page.get('url', '')}")

    synced_ids = {}
    if template_page_id:
        log.info("템플릿 적용 중 (synced_block 포함)...")
        synced_ids = copy_template_with_synced(notion, template_page_id, new_page["id"])
        log.info(f"  synced_block: {synced_ids}")

    return new_page, synced_ids, True


if __name__ == "__main__":
    import sys
    target_date = sys.argv[1] if len(sys.argv) > 1 else "2026-03-01"

    from datetime import date as dt
    d = dt.fromisoformat(target_date)
    day_names = ["월", "화", "수", "목", "금", "토", "일"]
    title = f"{target_date} ({day_names[d.weekday()]})"

    notion = get_client()
    log.info(f"=== 일간 Daily 페이지 추가: {target_date} ===\n")
    page, synced, is_new = create_daily_page(
        notion,
        title=title,
        date=target_date,
        year=f"{d.year}년",
        template_page_id=TEMPLATE_PAGE_ID,
    )
