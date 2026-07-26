"""테마 관심도 수집기.

각 테마의 검색 관심도를 같은 축에 올린 뒤, 최근 수준과 4주 전 대비 변화를 계산합니다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import yaml

from . import datalab

KST = timezone(timedelta(hours=9))


def _change(points: list[dict], days: int) -> float | None:
    """마지막 값 대비 days 일 전 값의 변화율(%).

    인덱스가 아니라 실제 날짜로 되짚습니다. 데이터랩이 저볼륨 구간을 빼고
    주면 '몇 칸 전'과 '며칠 전'이 어긋나기 때문입니다.
    """
    if not points:
        return None
    now = points[-1]["ratio"]
    target = datalab.shift_iso(points[-1]["period"], days)
    ref = datalab.value_on_or_before(points[:-1], target)
    if ref is None or ref["ratio"] <= 0:
        return None
    return round((now / ref["ratio"] - 1) * 100, 1)


def _percentile(points: list[dict]) -> float:
    """현재 값이 자기 이력에서 몇 번째 백분위인지."""
    values = sorted(p["ratio"] for p in points)
    if not values:
        return 0.0
    current = points[-1]["ratio"]
    below = sum(1 for v in values if v <= current)
    return round(below / len(values) * 100, 1)


def build(config_path: str = "config/themes.yaml") -> dict:
    with open(config_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    start, end = datalab.date_range(cfg["lookback_days"])
    time_unit = cfg.get("time_unit", "week")
    print(f"테마 관심도 수집: {start} ~ {end} ({time_unit})")

    merged = datalab.fetch(
        groups=cfg["groups"],
        anchor=cfg["anchor"],
        start_date=start,
        end_date=end,
        time_unit=time_unit,
    )
    merged = datalab.rescale_to_100(merged)

    # 날짜 기준으로 되짚습니다: 4주 = 28일, 12주 = 84일.
    span_short = 28
    span_long = 84

    themes = []
    for group in cfg["groups"]:
        name = group["groupName"]
        points = merged.get(name, [])
        if not points:
            print(f"  ! '{name}' 데이터가 비어 있습니다. 키워드를 확인하세요.")
            continue
        themes.append(
            {
                "name": name,
                "keywords": group["keywords"],
                "current": points[-1]["ratio"],
                "peak": max(p["ratio"] for p in points),
                "percentile": _percentile(points),
                "change_short": _change(points, span_short),
                "change_long": _change(points, span_long),
                "series": points,
            }
        )

    themes.sort(key=lambda t: (t["change_short"] is None, -(t["change_short"] or 0)))

    return {
        "sample": False,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "start_date": start,
        "end_date": end,
        "time_unit": time_unit,
        "span_short_label": "4주" if time_unit == "week" else "4주",
        "span_long_label": "12주" if time_unit == "week" else "12주",
        "themes": themes,
    }


def write(out_path: str = "data/themes.json") -> None:
    payload = build()
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"저장 완료: {out_path} (테마 {len(payload['themes'])}개)")
