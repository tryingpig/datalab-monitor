"""Notion 'Datalab-Monitor' 테마 온톨로지 DB → config 생성.

수집(collect) 직전에 돌려서, Notion 에 정의한 테마 목록을 읽어
데이터랩에 넣을 keyword 그룹(config/themes.groups.json)과
2단계용 메타(config/themes.meta.json: 편입종목·동의어·분류)를 만든다.

역할 분리(중요):
- 검색어  → 데이터랩 검색 그룹. 그 테마 '자체'의 검색 관심도를 잰다.
- 편입종목 → 데이터랩에 넣지 않는다(삼성전자 등 대형주 검색은 대부분 테마와
  무관해 신호를 오염시킴). 애널 다이제스트에서 테마 거론을 세는 2단계 축.

토큰: 환경변수 NOTION_TOKEN (Actions Secret, rs-tracker 와 동일 토큰).
실패/토큰없음: 기존 themes.groups.json 이 있으면 유지(폴백), 없으면 no-op
→ themes.py 가 config/themes.yaml 의 정적 groups 로 되돌아간다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DB_ID = "3aaebba0843a80759b63e8fcd6fc15ee"  # Notion 'Datalab-Monitor'
BASE = "https://api.notion.com/v1"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
GROUPS_OUT = CONFIG_DIR / "themes.groups.json"
META_OUT = CONFIG_DIR / "themes.meta.json"

MAX_KEYWORDS = 20  # 데이터랩 그룹당 상한


def _api(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _text(prop: dict | None) -> str:
    if not prop:
        return ""
    arr = prop.get("rich_text") or prop.get("title") or []
    return "".join(t.get("plain_text", "") for t in arr).strip()


def _csv_list(prop: dict | None) -> list[str]:
    raw = _text(prop)
    return [x.strip() for x in raw.split(",") if x.strip()]


def _date_start(prop: dict | None) -> str | None:
    d = (prop or {}).get("date") or {}
    return d.get("start")


def fetch_themes(token: str) -> tuple[list[dict], dict]:
    groups: list[dict] = []
    meta: dict = {}
    cursor = None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        res = _api("POST", f"/databases/{DB_ID}/query", token, payload)
        for row in res["results"]:
            p = row["properties"]
            if not p.get("활성", {}).get("checkbox", False):
                continue
            name = _text(p.get("이름"))
            keywords = _csv_list(p.get("검색어"))[:MAX_KEYWORDS]
            if not name or not keywords:
                continue
            sector = (p.get("분류", {}).get("select") or {}).get("name", "")
            first_seen = _date_start(p.get("first_seen"))
            # groups.json 은 수집(검색그룹) + 표시(대분류·신규배지)에 함께 쓰인다.
            groups.append({
                "groupName": name,
                "keywords": keywords,
                "sector": sector,
                "first_seen": first_seen,
            })
            meta[name] = {
                "stocks": _csv_list(p.get("편입종목")),
                "synonyms": _csv_list(p.get("동의어")),
                "sector": sector,
                "first_seen": first_seen,
                "last_seen": _date_start(p.get("last_seen")),
            }
        if not res.get("has_more"):
            break
        cursor = res["next_cursor"]
    return groups, meta


def _write(groups: list[dict], meta: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(GROUPS_OUT, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)
    with open(META_OUT, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def main() -> int:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        if GROUPS_OUT.exists():
            print("NOTION_TOKEN 없음 → 기존 themes.groups.json 유지(폴백)", file=sys.stderr)
        else:
            print("NOTION_TOKEN 없음 → themes.yaml 정적 groups 사용", file=sys.stderr)
        return 0

    try:
        groups, meta = fetch_themes(token)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        detail = ""
        if isinstance(exc, urllib.error.HTTPError):
            detail = exc.read().decode("utf-8", "replace")[:300]
        print(f"Notion 조회 실패({exc}) {detail} → 기존 config 유지(폴백)", file=sys.stderr)
        return 0  # 수집을 막지 않는다

    if not groups:
        print("활성 테마가 0개입니다. 기존 config 유지(폴백).", file=sys.stderr)
        return 0

    _write(groups, meta)
    print(f"Notion 동기화 완료: 테마 {len(groups)}개 → {GROUPS_OUT.name}, {META_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
