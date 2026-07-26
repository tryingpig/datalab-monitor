"""테마 관심도 수집기.

1년치를 일간으로 한 번 받아 같은 축에 올린 뒤, 1개월/3개월/6개월/1년 각 기간별로
변화율·기간최고·백분위를 미리 계산합니다. 화면은 버튼으로 기간을 바꾸며 봅니다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import yaml

from . import datalab

KST = timezone(timedelta(hours=9))


def _moving_average(points: list[dict], window: int) -> list[dict]:
    """일간 데이터의 튐을 줄이는 이동평균. period 는 유지, ratio 만 평활."""
    if window <= 1 or not points:
        return points
    values = [p["ratio"] for p in points]
    out = []
    for i in range(len(points)):
        chunk = values[max(0, i - window + 1) : i + 1]
        out.append({"period": points[i]["period"], "ratio": round(sum(chunk) / len(chunk), 4)})
    return out


def _window_stats(points: list[dict], days: int) -> dict:
    """최근 days 구간의 변화율·기간최고·백분위. 날짜 기준으로 자릅니다."""
    last = points[-1]
    target = datalab.shift_iso(last["period"], days)
    window = [p for p in points if p["period"] > target] or points

    ref = datalab.value_on_or_before(points[:-1], target)
    if ref is None and window[0]["period"] < last["period"]:
        ref = window[0]  # 기간이 보유 데이터보다 길면 가진 범위의 시작점 기준
    if ref and ref["ratio"] > 0:
        change = round((last["ratio"] / ref["ratio"] - 1) * 100, 1)
    else:
        change = None

    values = [p["ratio"] for p in window]
    peak = max(values)
    below = sum(1 for v in values if v <= last["ratio"])
    percentile = round(below / len(values) * 100, 1)

    return {"change": change, "peak": round(peak, 2), "percentile": percentile}


def build(config_path: str = "config/themes.yaml") -> dict:
    with open(config_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    start, end = datalab.date_range(cfg["lookback_days"])
    time_unit = cfg.get("time_unit", "date")
    print(f"테마 관심도 수집: {start} ~ {end} ({time_unit})")

    merged = datalab.fetch(
        groups=cfg["groups"],
        anchor=cfg["anchor"],
        start_date=start,
        end_date=end,
        time_unit=time_unit,
    )

    smooth = cfg.get("smooth_days", 7)
    merged = {name: _moving_average(pts, smooth) for name, pts in merged.items()}
    merged = datalab.rescale_to_100(merged)

    windows = cfg["windows"]

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
                "windows": {w["key"]: _window_stats(points, w["days"]) for w in windows},
                "series": points,
            }
        )

    default_window = cfg.get("default_window", windows[0]["key"])
    # 기본 기간의 변화율로 미리 정렬해 둡니다(화면에서 기간 바꾸면 다시 정렬).
    themes.sort(
        key=lambda t: (
            t["windows"][default_window]["change"] is None,
            -(t["windows"][default_window]["change"] or 0),
        )
    )

    return {
        "sample": False,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "start_date": start,
        "end_date": end,
        "time_unit": time_unit,
        "windows": windows,
        "default_window": default_window,
        "themes": themes,
    }


def write(out_path: str = "data/themes.json") -> None:
    payload = build()
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"저장 완료: {out_path} (테마 {len(payload['themes'])}개)")
